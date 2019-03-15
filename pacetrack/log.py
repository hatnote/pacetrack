import os

from lithoxyl import Logger, SensibleSink, SensibleFormatter, StreamEmitter, SensibleFilter
from lithoxyl.emitters import FileEmitter

CUR_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_PATH = os.path.dirname(CUR_PATH)
LOG_PATH = PROJECT_PATH + '/pacetrack.log'


tlog = Logger('pacetrack')
file_fmt = SensibleFormatter('{status_char}{iso_end_notz} - {duration_s}s - {action_name} - {end_message}',
                             begin='{status_char}{iso_begin_notz} -   --   - {action_name} - {begin_message}')


def build_stream_sink(stream):
    emt = StreamEmitter(stream)
    file_filter = SensibleFilter(success='info',
                                 failure='debug',
                                 exception='debug')
    file_sink = SensibleSink(formatter=file_fmt,
                             emitter=emt,
                             filters=[file_filter])
    return file_sink



default_file_sink = build_stream_sink(open(LOG_PATH, 'a'))
tlog.add_sink(default_file_sink)


stdout_fmt = file_fmt
stdout_emt = StreamEmitter('stderr')
stdout_filter = SensibleFilter(success='critical',
                               failure='debug',
                               exception='debug')
stdout_sink = SensibleSink(formatter=stdout_fmt,
                           emitter=stdout_emt,
                           filters=[stdout_filter])
tlog.add_sink(stdout_sink)
