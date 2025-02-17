from fastapi import FastAPI
from .routers import agent_exec

app = FastAPI()
# initilizing our application

#app.include_router(router=questions_and_answers.router)
app.include_router(router=agent_exec.router)
# including our routers (in this case only one), to the application