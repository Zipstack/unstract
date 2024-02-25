# Generating fixtures for tests

Seeding data into the DB can help create fixtures to run tests with a custom set of records that gets reset after every run.

## Seeding

In order to seed data into the DB for the first time, we update and make use of `seed_data.py` to create the necessary records.

Run the following to insert records.

```
python manage.py shell < utils/seed_data/seed_data.py
```

## Fixture generation

The inserted records/state needs to be dumped to a fixture with the following

```
python manage.py dumpdata <app_name> --indent 4 > <path_to_filename>.json
```

Subsequently this can be used to load data (or) reset back to this initial state with the following

```
python manage.py loaddata <path_to_filename>.json
```
