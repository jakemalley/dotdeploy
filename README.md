# dotdeploy

A simple dotfile deployment system written in Python (Currently a work in progress!)

# installation

Using Pip:
```
pip install .
```

Manually (as a standalone script)
```
cp dotdeploy/dotdeploy.py /usr/local/bin/dotdeploy
chmod +x /usr/local/bin/dotdeploy
```

## usage

```
./dotdeploy apply docs/example.ini
```

## development

#### create environment

```
# create virtual environment
python3 -m venv venv
# activate environment
source venv/bin/activate
# install dotdeploy editable with dev requirements
pip install --editable ".[dev]"
```

#### running unittests

```
./test.sh
```