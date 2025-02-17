----- step 1
all installs you will need:
pip install fastapi uvicorn sqlalchemy psycopg2-binary pydantic langchain langchain-openai python-dotenv

----- step 2
you will also need to create a database within pg admin, to do this download prosgres and register a server, make sure the database you created has the same info in the database.py

----- step 3
to start the program, make sure you are in the LangChainApp directory to do this from the folder directory do:
cd api
cd LangChainApp

----- step 4
then type:
uvicorn main:app --reload
