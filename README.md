# dotdeploy

A simple dotfile deployment system written in Python (Currently a work in progress!)

## usage

```
./dotdeploy apply example.ini
```

## development

#### create environment

```
# create virtual environment
python3 -m venv venv
# activate environment
source venv/bin/activate
# install requirements
pip install pylint black mock coverage nose2
```

#### running unittests

```
./test.sh
```