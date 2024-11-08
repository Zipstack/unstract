# Print Release Notes

Accepts `current_version` and `target_version` as inputs to print the necessary release notes / warnings to be shown while updating a release

Run below to get more information on the usage

```shell
python print_release_notes.py -h
```

Make sure to create / activate a virtual environment with the below commands

```shell
pdm venv create -w virtualenv --with-pip
eval $(pdm venv activate in-project)    
```
