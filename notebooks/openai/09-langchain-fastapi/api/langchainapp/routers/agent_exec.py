import asyncio
import sys
print(sys.executable)
from langchain.callbacks.base import AsyncCallbackHandler

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_openai import ChatOpenAI

# creating our own "sub-application" and using a unique 
# prefix and tag to add it's own endpoints in the program
router = APIRouter(prefix='/agent-exec', tags=['agent-exec'])

# setting up openai, you should store your key inside the "OPENAI_API_KEY" variable
OPENAI_API_KEY = ""

# this connects the LLM (gpt-4o) to langchains chat model, making this easily accessible for us.
llm = ChatOpenAI(
    model_name="gpt-4o",
    temperature=0.0,
    streaming=True,
    openai_api_key=OPENAI_API_KEY
)

from langchain_core.tools import tool

"""
Now we will define a few tools to be used by an async agent executor. Our goal for tool-use in regards to streaming are:

* The tool-use steps will be streamed in one big chunk, ie we do not return the tool use information token-by-token but instead it streams message-by-message.

* The final LLM output _will_ be streamed token-by-token as we saw above.

For these we need to define a few math tools and our final answer tool.
"""

@tool
def add(x: float, y: float) -> float:
    """Add 'x' and 'y'."""
    return x + y

@tool
def multiply(x: float, y: float) -> float:
    """Multiply 'x' and 'y'."""
    return x * y

@tool
def exponentiate(x: float, y: float) -> float:
    """Raise 'x' to the power of 'y'."""
    return x ** y

@tool
def subtract(x: float, y: float) -> float:
    """Subtract 'x' from 'y'."""
    return y - x

@tool
def final_answer(answer: str, tools_used: list[str]) -> str:
    """Use this tool to provide a final answer to the user.
    The answer should be in natural language as this will be provided
    to the user directly. The tools_used must include a list of tool
    names that were used within the `scratchpad`. You MUST use this tool
    to conclude the interaction.
    """
    return {"answer": answer, "tools_used": tools_used}

tools = [add, multiply, exponentiate, subtract, final_answer]

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

"""

We will create our `ChatPromptTemplate`, using a system message, chat history, user input, and a scratchpad for intermediate steps.

"""

prompt = ChatPromptTemplate.from_messages([
    ("system", (
        "You're a helpful assistant. When answering a user's question "
        "you should first use one of the tools provided. After using a "
        "tool the tool output will be provided back to you. You MUST "
        "then use the final_answer tool to provide a final answer to the user. "
        "DO NOT use the same tool more than once."
    )),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

from langchain_core.runnables.base import RunnableSerializable

tools = [add, subtract, multiply, exponentiate, final_answer]

"""

As before, we will define our `agent` with LCEL.

"""

# define the agent runnable
agent: RunnableSerializable = (
    {
        "input": lambda x: x["input"],
        "chat_history": lambda x: x["chat_history"],
        "agent_scratchpad": lambda x: x.get("agent_scratchpad", [])
    }
    | prompt
    | llm.bind_tools(tools, tool_choice="any")
)

import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

# create tool name to function mapping
name2tool = {tool.name: tool.func for tool in tools}

"""

Finally, we will create the agent executor.

"""

class CustomAgentExecutor:
    chat_history: list[BaseMessage]

    def __init__(self, max_iterations: int = 3):
        self.chat_history = []
        self.max_iterations = max_iterations
        self.agent: RunnableSerializable = (
            {
                "input": lambda x: x["input"],
                "chat_history": lambda x: x["chat_history"],
                "agent_scratchpad": lambda x: x.get("agent_scratchpad", [])
            }
            | prompt
            | llm.bind_tools(tools, tool_choice="any")  # we're forcing tool use again
        )

    def invoke(self, input: str) -> dict:
        # invoke the agent but we do this iteratively in a loop until
        # reaching a final answer
        count = 0
        agent_scratchpad = []
        while count < self.max_iterations:
            # invoke a step for the agent to generate a tool call
            out = self.agent.invoke({
                "input": input,
                "chat_history": self.chat_history,
                "agent_scratchpad": agent_scratchpad
            })
            # if the tool call is the final answer tool, we stop
            if out.tool_calls[0]["name"] == "final_answer":
                break
            agent_scratchpad.append(out)  # add tool call to scratchpad
            # otherwise we execute the tool and add it's output to the agent scratchpad
            tool_out = name2tool[out.tool_calls[0]["name"]](**out.tool_calls[0]["args"])
            # add the tool output to the agent scratchpad
            action_str = f"The {out.tool_calls[0]['name']} tool returned {tool_out}"
            agent_scratchpad.append({
                "role": "tool",
                "content": action_str,
                "tool_call_id": out.tool_calls[0]["id"]
            })
            # add a print so we can see intermediate steps
            print(f"{count}: {action_str}")
            count += 1
        # add the final output to the chat history
        final_answer = out.tool_calls[0]["args"]
        # this is a dictionary, so we convert it to a string for compatibility with
        # the chat history
        final_answer_str = json.dumps(final_answer)
        self.chat_history.append({"input": input, "output": final_answer_str})
        self.chat_history.extend([
            HumanMessage(content=input),
            AIMessage(content=final_answer_str)
        ])
        # return the final answer in dict form
        return final_answer
    
agent_executor = CustomAgentExecutor()

@router.get("/invoke-response")
async def invoke_response(query: str):
    return agent_executor.invoke(query)

from langchain_core.runnables import ConfigurableField

"""

Let's modify our `agent_executor` to use streaming and parse the streamed output into a 
format that we can more easily work with.

First, when streaming with our custom agent executor we will need to pass our callback 
handler to the agent on every new invocation. To make this simpler we can make the 
`callbacks` field a configurable field and this will allow us to initialize the agent 
using the `with_config` method, allowing us to pass the callback handler to the agent 
with every invocation.

"""

llm = ChatOpenAI(
    model_name="gpt-4o-mini",
    temperature=0.0,
    streaming=True,
    openai_api_key=OPENAI_API_KEY
).configurable_fields(
    callbacks=ConfigurableField(
        id="callbacks",
        name="callbacks",
        description="A list of callbacks to use for streaming",
    )
)

# define the agent runnable
agent: RunnableSerializable = (
    {
        "input": lambda x: x["input"],
        "chat_history": lambda x: x["chat_history"],
        "agent_scratchpad": lambda x: x.get("agent_scratchpad", [])
    }
    | prompt
    | llm.bind_tools(tools, tool_choice="any")
)

import asyncio

from langchain.callbacks.base import AsyncCallbackHandler



class QueueCallbackHandler(AsyncCallbackHandler):
    """Callback handler that puts tokens into a queue."""
    
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self.final_answer_seen = False

    async def __aiter__(self):
        while True:
            if self.queue.empty():
                await asyncio.sleep(0.1)
                continue
            token_or_done = await self.queue.get()

            if token_or_done == "<<DONE>>":
                # this means we're done
                return
            if token_or_done:
                yield token_or_done
    
    async def on_llm_new_token(self, *args, **kwargs) -> None:
        """Put new token in the queue."""
        #print(f"on_llm_new_token: {args}, {kwargs}")
        chunk = kwargs.get("chunk")
        if chunk:
            # check for final_answer tool call
            if tool_calls := chunk.message.additional_kwargs.get("tool_calls"):
                if tool_calls[0]["function"]["name"] == "final_answer":
                    # this will allow the stream to end on the next `on_llm_end` call
                    self.final_answer_seen = True
        self.queue.put_nowait(kwargs.get("chunk"))
        return
    
    async def on_llm_end(self, *args, **kwargs) -> None:
        """Put None in the queue to signal completion."""
        #print(f"on_llm_end: {args}, {kwargs}")
        # this should only be used at the end of our agent execution, however LangChain
        # will call this at the end of every tool call, not just the final tool call
        # so we must only send the "done" signal if we have already seen the final_answer
        # tool call
        if self.final_answer_seen:
            self.queue.put_nowait("<<DONE>>")
        else:
            self.queue.put_nowait("<<STEP_END>>")
        return
    
queue = asyncio.Queue()
streamer = QueueCallbackHandler(queue)

async def stream(query: str):
    response = agent.with_config(
        callbacks=[streamer]
    )
    async for token in response.astream({
        "input": query,
        "chat_history": [],
        "agent_scratchpad": []
    }):
        print(token, flush=True)

from langchain_core.messages import ToolMessage

class CustomAgentExecutor:
    chat_history: list[BaseMessage]

    def __init__(self, max_iterations: int = 3):
        self.chat_history = []
        self.max_iterations = max_iterations
        self.agent: RunnableSerializable = (
            {
                "input": lambda x: x["input"],
                "chat_history": lambda x: x["chat_history"],
                "agent_scratchpad": lambda x: x.get("agent_scratchpad", [])
            }
            | prompt
            | llm.bind_tools(tools, tool_choice="any")  # we're forcing tool use again
        )

    async def invoke(self, input: str, streamer: QueueCallbackHandler, verbose: bool = False) -> dict:
        # invoke the agent but we do this iteratively in a loop until
        # reaching a final answer
        count = 0
        agent_scratchpad = []
        while count < self.max_iterations:
            # invoke a step for the agent to generate a tool call
            async def stream(query: str):
                response = self.agent.with_config(
                    callbacks=[streamer]
                )
                # we initialize the output dictionary that we will be populating with
                # our streamed output
                output = None
                # now we begin streaming
                async for token in response.astream({
                    "input": query,
                    "chat_history": self.chat_history,
                    "agent_scratchpad": agent_scratchpad
                }):
                    if output is None:
                        output = token
                    else:
                        # we can just add the tokens together as they are streamed and
                        # we'll have the full response object at the end
                        output += token
                    if token.content != "":
                        # we can capture various parts of the response object
                        if verbose: print(f"content: {token.content}", flush=True)
                    tool_calls = token.additional_kwargs.get("tool_calls")
                    if tool_calls:
                        if verbose: print(f"tool_calls: {tool_calls}", flush=True)
                        tool_name = tool_calls[0]["function"]["name"]
                        if tool_name:
                            if verbose: print(f"tool_name: {tool_name}", flush=True)
                        arg = tool_calls[0]["function"]["arguments"]
                        if arg != "":
                            if verbose: print(f"arg: {arg}", flush=True)
                return AIMessage(
                    content=output.content,
                    tool_calls=output.tool_calls,
                    tool_call_id=output.tool_calls[0]["id"]
                )

            tool_call = await stream(query=input)
            # add initial tool call to scratchpad
            agent_scratchpad.append(tool_call)
            # otherwise we execute the tool and add it's output to the agent scratchpad
            tool_name = tool_call.tool_calls[0]["name"]
            tool_args = tool_call.tool_calls[0]["args"]
            tool_call_id = tool_call.tool_call_id
            tool_out = name2tool[tool_name](**tool_args)
            # add the tool output to the agent scratchpad
            tool_exec = ToolMessage(
                content=f"{tool_out}",
                tool_call_id=tool_call_id
            )
            agent_scratchpad.append(tool_exec)
            count += 1
            # if the tool call is the final answer tool, we stop
            if tool_name == "final_answer":
                break
        # add the final output to the chat history, we only add the "answer" field
        final_answer = tool_out["answer"]
        self.chat_history.extend([
            HumanMessage(content=input),
            AIMessage(content=final_answer)
        ])
        # return the final answer in dict form
        return tool_args
    
agent_executor = CustomAgentExecutor()

async def token_generator(query: str, streamer):
        task = asyncio.create_task(agent_executor.invoke(query, streamer))
        async for token in streamer:
            if token == "<<STEP_END>>":
                yield "\n\n"
            # we'll first identify if the token is a tool call
            elif tool_calls := token.message.additional_kwargs.get("tool_calls"):
                if tool_name := tool_calls[0]["function"]["name"]:
                    yield tool_name
                # if we have a tool call with arguments, we add them to our args string
                if tool_args := tool_calls[0]["function"]["arguments"]:
                    yield tool_args
        await task

@router.get("/stream-response")
async def stream_response(query: str):

    queue = asyncio.Queue()
    streamer = QueueCallbackHandler(queue)

    gen = token_generator(query, streamer)

    return StreamingResponse(gen, media_type="text/plain")