# AmCAT4

API server for AmCAT4 Text Analysis

# Installation

## Elasticsearch

AmCAT requires an elasticsearch instance. The easiest way to run one for development is using docker:

```
sudo docker run -p 9200:9200 -p 9300:9300 -e "discovery.type=single-node" docker.elastic.co/elasticsearch/elasticsearch:6.5.4
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
