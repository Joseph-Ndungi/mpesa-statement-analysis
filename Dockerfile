# syntax=docker/dockerfile:1

#base image to use
FROM python:3.8-slim-buster

#folder to use for the rest of operations
WORKDIR /python-docker

#copy requirements into containers image
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

#copy remainder of the files
COPY . .

#instruct docker to run our flask app as a module
#pass the port
CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0"]