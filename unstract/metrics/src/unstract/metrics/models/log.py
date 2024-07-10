from elasticsearch_dsl import Date, InnerDoc, Keyword, Text


class Log(InnerDoc):
    level = Keyword()
    time = Date()
    message = Text()
