import asyncio

from agent import QueueCallbackHandler, agent_executor
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# initilizing our application
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# streaming function
async def token_generator(content: str, streamer: QueueCallbackHandler):
    task = asyncio.create_task(agent_executor.invoke(
        input=content,
        streamer=streamer,
        verbose=False  # set to True to see verbose output in console
    ))
    # initialize various components to stream
    async for token in streamer:
        if token == "<<STEP_END>>":
            # send end of step token
            yield "</step>"
        elif tool_calls := token.message.additional_kwargs.get("tool_calls"):
            if tool_name := tool_calls[0]["function"]["name"]:
                # send start of step token followed by step name tokens
                yield f"<step><step_name>{tool_name}</step_name>"
            if tool_args := tool_calls[0]["function"]["arguments"]:
                # tool args are streamed directly
                yield tool_args
    await task

# invoke function
@app.post("/invoke")
async def invoke(content: str):
    queue: asyncio.Queue = asyncio.Queue()
    streamer = QueueCallbackHandler(queue)
    # return the streaming response
    return StreamingResponse(
        token_generator(content, streamer),
        media_type="text/plain"
    )
