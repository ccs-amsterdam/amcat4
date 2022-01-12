
![Build status](https://github.com/ccs-amsterdam/amcat4/actions/workflows/unittests.yml/badge.svg)

# AmCAT4

Server for document management and automatic text analysis, developed as part of [OPTED](https://opted.eu). 
[Learn more](https://opted.eu/fileadmin/user_upload/k_opted/OPTED_deliverable_D7.1.pdf)

See also the [API Documentation](apidoc.md)

## Elasticsearch

AmCAT requires an elasticsearch instance. The easiest way to run one for development is using docker:

```
sudo docker run --name elastic7 -dp 9200:9200 -p 9300:9300 -e "discovery.type=single-node" docker.elastic.co/elasticsearch/elasticsearch:7.11.1
```

## Installing from PyPi

To install and run AmCAT4 from pypi simply run:

```
pip3 install amcat4
python3 -m amcat4 run
```

## Installing from source

To install AmCAT4 from github and create a virutal environment, run:

```
git clone https://github.com/ccs-amsterdam/amcat4
cd amcat4
python3 -m venv env
env/bin/pip install -e .
env/bin/python -m amcat4 run
```

To run the unit tests:

```
env/bin/pip install nose
env/bin/nosetests
```

(obviously, feel free to place your virtaal environment in any other location, this is just how I set things up)



