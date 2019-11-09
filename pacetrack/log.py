import os

from lithoxyl import Logger, SensibleSink, SensibleFormatter, StreamEmitter, SensibleFilter
from lithoxyl.emitters import FileEmitter

CUR_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_PATH = os.path.dirname(CUR_PATH)
LOG_PATH = PROJECT_PATH + '/pacetrack.log'
JSUB_LOG_PATH = PROJECT_PATH + '/jsub_logs/'


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


stderr_fmt = file_fmt
stderr_emt = StreamEmitter('stderr')
stderr_filter = SensibleFilter(success='critical',
                               failure='debug',
                               exception='debug')
stderr_sink = SensibleSink(formatter=stderr_fmt,
                           emitter=stderr_emt,
                           filters=[stderr_filter])


def enable_debug_log():
    tlog.add_sink(stderr_sink)
