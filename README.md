[![Build Status](https://travis-ci.org/ccs-amsterdam/amcat4.svg?branch=master)](https://travis-ci.org/ccs-amsterdam/amcat4)
[![codecov](https://codecov.io/gh/ccs-amsterdam/amcat4/branch/master/graph/badge.svg)](https://codecov.io/gh/ccs-amsterdam/amcat4)

# AmCAT4

API server for AmCAT4 Text Analysis

# Installation

## Elasticsearch

AmCAT requires an elasticsearch instance. The easiest way to run one for development is using docker:

```
sudo docker run --name elastic7 -dp 9200:9200 -p 9300:9300 -e "discovery.type=single-node" docker.elastic.co/elasticsearch/elasticsearch:7.11.1
```

## From PyPi

To install and run AmCAT4 from pypi simply run:

```
pip3 install amcat4
python3 -m amcat4
```

## From source

To install AmCAT4 from github and create a virutal environment, run:

```
git clone https://github.com/ccs-amsterdam/amcat4
cd amcat4
python3 -m venv env
env/bin/pip install -e .
env/bin/python -m amcat4
```

To run the unit tests:

```
env/bin/pip install nose
env/bin/nosetests
```

(obviously, feel free to place your virutal environment in any other location, this is just how I set things up)
