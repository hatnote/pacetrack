import os

from lithoxyl import Logger, SensibleSink, SensibleFormatter, StreamEmitter, SensibleFilter
from lithoxyl.emitters import FileEmitter

CUR_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_PATH = os.path.dirname(CUR_PATH)
LOG_PATH = PROJECT_PATH + '/pacetrack.log'


class FixedFileEmitter(FileEmitter):
    def __init__(self, filepath, encoding=None, **kwargs):
        self.encoding = encoding
        super(FixedFileEmitter, self).__init__(filepath, encoding, **kwargs)





tlog = Logger('pacetrack')

file_fmt = SensibleFormatter('{parent_depth_indent}{status_char}{iso_end_notz} - {duration_s}s - {action_name} - {end_message}',
                             begin='{parent_depth_indent}{status_char}{iso_begin_notz} - {action_name} - {begin_message}')
file_emt = FixedFileEmitter(LOG_PATH)
file_filter = SensibleFilter(success='info',
                             failure='debug',
                             exception='debug')
file_sink = SensibleSink(formatter=file_fmt,
                         emitter=file_emt,
                         filters=[file_filter])
tlog.add_sink(file_sink)


stdout_fmt = file_fmt
stdout_emt = StreamEmitter('stdout')
stdout_filter = SensibleFilter(success='critical',
                               failure='debug',
                               exception='debug')
stdout_sink = SensibleSink(formatter=stdout_fmt,
                           emitter=stdout_emt,
                           filters=[stdout_filter])
tlog.add_sink(stdout_sink)



def set_debug(enable=True):
    if not enable:
        raise NotImplementedError()
    dbg_fmtr = file_fmt
    dbg_emtr = StreamEmitter('stderr')

    dbg_sink = SensibleSink(formatter=dbg_fmtr,
                            emitter=dbg_emtr)
    tlog.add_sink(dbg_sink)
