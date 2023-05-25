import sched
import time
import re
from datetime import timedelta
import datetime
from dateutil.relativedelta import relativedelta




def parse_time_string(self, date_str):
    # second_regex = re.compile(r'(\d+)\s*s(ec)?(ond)(s)?')
    # minute_regex = re.compile(r'(\d+)\s*m(?!o)(in)?(ute)?(s)?')
    # hour_regex   = re.compile(r'(\d+)\s*h(?ou)?(?r)?(s)?')
    # day_regex    = re.compile(r'(\d+)\s*d(ay)?(s)?')
    # week_regex   = re.compile(r'(\d+)\s*w(eek)?(s)?')
    # month_regex  = re.compile(r'(\d+)\s*mo(nth)?(s)?')
    # year_regex   = re.compile(r'(\d+)\s*y(ear)?(s)?')
    full_date_regex = re.compile((r'(((?P<seconds>\d+)\s*s(?:ec)?(?:ond)?(?:s)?)|'
    r'((?P<minutes>\d+)\s*m(?!o)(?:in)?(?:ute)?(?:s)?)|'
    r'((?P<hours>\d+)\s*h(?:ou)?(?:r)?(?:s)?)|'
    r'((?P<days>\d+)\s*d(?:ay)?(?:s)?)|'
    r'((?P<weeks>\d+)\s*w(?:ee)?(?:k)?(?:s)?)|'
    r'((?P<months>\d+)\s*mo(?:nth)?(?:s))|'
    r'((?P<years>\d+)\s*y(?:ea)?(?:r)?(?:s)?))'))
    all_parts = [x for x in full_date_regex.finditer(date_str)]
    datetime_parts = {}
    for part in all_parts:
        for name, param in part.groupdict().items():
            if param:
                print(f'name: {name}')
                print(f'param: {param}')
                if datetime_parts.get(name):
                    datetime_parts[name] += int(param)
                else:
                    datetime_parts[name] = int(param)
    new_date = datetime.datetime.now()
    diff_date = relativedelta(new_date, **datetime_parts)
    return new_date + diff_date


print(parse_time_string('','68 years, 1 months, 1 day, 1hr 1min'))
print(parse_time_string('','30min'))
print(parse_time_string('','1hr30min'))