FROM python:3.12

# update and install required packages
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-setuptools \
    && apt-get autoremove -y

# set working directory
WORKDIR /tmp

# copy requirements.txt
COPY requirements.txt .

# install requirements
RUN pip install --no-cache-dir -r requirements.txt