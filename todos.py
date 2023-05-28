from __future__ import annotations

from tinydb import TinyDB, Query, Storage
import yaml

import dateutil.parser
import datetime
import pytz


class ToDoException(Exception):
    """ An exception that when raised will show a detailed message to the reminders.remove(Query().task == task_id)user """
    def __init__(self, msg:str):
        super().__init__(self)
        self.msg = msg
    def __str__(self) -> str:
        return f"ToDoException: {self.msg}"


def format_name(name:str):
    """ Defines the format `name` fields in the database must adhere to """
    return name.strip().lower().replace(" ", "_")


DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%Y-%m-%d %X"
TIMEZONE = "Europe/Brussels"

PARSERINFO = dateutil.parser.parserinfo(dayfirst=True)


def datetime_from_string(time:str, format=None):
    """ Determines a datetime from a string. If a format is passed, the datetime is formatted into a string again. """
    try:
        dt = dateutil.parser.parse(time, PARSERINFO).astimezone(pytz.timezone(TIMEZONE))
        if format:
            return dt.strftime(format)
        else:
            return dt
    except dateutil.parser.ParserError as e:
        raise ToDoException(f"Was unable to parse the string `{time}` as a time. To be sure, format times as `yyyy-mm-dd hh:mm`,\
                             but most English-language strings should be fine.")

def timestamp_from_string(time:str):
    try:
        dt = dateutil.parser.parse(time).astimezone(pytz.timezone("Europe/Brussels"))
        return int(datetime.datetime.timestamp(dt))
    except dateutil.parser.ParserError as e:
        raise ToDoException(f"Was unable to parse the string `{time}` as a time. To be sure, format times as `yyyy-mm-dd hh:mm`,\
                             but most English-language strings should be fine.")


class YAMLStorage(Storage):
    def __init__(self, filename):
        self.filename = filename
        with open(filename, 'a'): # creates the file if it doesn't exist
            pass

    def read(self):
        with open(self.filename) as handle:
            try:
                data = yaml.safe_load(handle.read())
                return data
            except yaml.YAMLError:
                return None

    def write(self, data):
        with open(self.filename, 'w+') as handle:
            yaml.dump(data, handle)

    def close(self):
        pass

# /data is the persistent volume provided by docker/podman
# if you want to run this outside of a container, just use "db.json"
db = TinyDB("/data/db.yml", storage=YAMLStorage)


class Person:
    table = db.table('people')

    name: str # the unique identifier with which to refer to the person
    pretty_name: str # the nicely formatted string used in to-do list printing
    id: str # discord's numerical id for the user's account (this should be a string!)

    def __init__(self, _person):
        self.doc_id = _person.doc_id
        self.name = _person['name']
        self.pretty_name = _person['pretty_name']
        self.id = _person['id']

    @classmethod
    def from_name(cls, name:str) -> Person:
        name = format_name(name)
        _person = cls.table.get(Query().name == name)
        if _person:
            return cls(_person)
        else:
            return None
    
    @classmethod
    def from_id(cls, id:str) -> Person:
        _person = cls.table.get(Query().id == id)
        if _person:
            return cls(_person)
        else:
            return None
    
    @classmethod
    def new_person(cls, name:str, pretty_name:str, id:str) -> Person:
        name = format_name(name)
        if cls.from_name(name):
            raise ToDoException(f"A person with name `{name}` already exists.")
        if cls.from_id(id):
            raise ToDoException(f"A person with id `{id}` already exists.")
        doc_id = cls.table.insert({'name': name, 'pretty_name': pretty_name, 'id': id})
        return cls(cls.table.get(doc_id=doc_id))
    
    @classmethod
    def remove_person(cls, name:str):
        name = format_name(name)
        cls.table.remove(Query().name == name)
        for task in Task.table.search(Query().name == name):
            Reminder.table.remove(Query().name == name)
            Task.remove_task(task.doc_id)
    
    def add_task(self, content, deadline:str=None) -> Task:
        if not content:
            raise ToDoException(f"Cannot add an empty task to the to-do list...")
        if deadline:
            deadline = datetime_from_string(deadline, DATE_FMT)
            task_id = Task.table.insert({'name': self.name, 'content': content, 'deadline': deadline})
        else:
            task_id = Task.table.insert({'name': self.name, 'content': content})
        return Task.from_id(task_id)

    def todos(self):
        return [
            Task(_task) for _task in Task.table.search(Query().name == self.name)
        ]

    def todo_list(self) -> str:
        _todo_list = ""
        for task in self.todos():
            _todo_list += str(task) + "\n"
        return _todo_list

    def reminders(self):
        return [
            Reminder(_reminder) for _reminder in Reminder.table.search(Query().names.any([self.name]))
        ]

    def reminder_list(self) -> str:
        _reminder_list = ""
        for reminder in self.reminders():
            _reminder_list += str(reminder) + "\n"
        return _reminder_list


class Task:
    table = db.table('tasks')

    name: str # the person to whom the task belongs (format: all lowercase)
    content: str # the task content
    deadline : str | None # [optional] the date by which the task should be completed at the latest (format: yyyy-mm-dd)
    
    def __init__(self, _task):
        self.doc_id = _task.doc_id
        self.name = _task['name']
        self.content = _task['content']
        self.deadline = _task['deadline'] if 'deadline' in _task else None

    def __str__(self):
        if self.deadline:
            return f"**[{self.doc_id}]** {self.content} *(deadline: {self.deadline})*"
        else:
            return f"**[{self.doc_id}]** {self.content}"

    @classmethod
    def from_id(cls, task_id:int) -> Task:
        _task = cls.table.get(doc_id=task_id)
        if _task:
            return cls(_task)
        else:
            return None
    
    @classmethod
    def remove_task(cls, task_id:int) -> Task:
        task = cls.from_id(task_id)
        if task:
            Task.table.remove(doc_ids=[task_id])
            Reminder.table.remove(Query().task == task_id)
        return task


class Reminder:
    table = db.table('reminders')

    time: str # the date to post the reminder (format: yyyy-mm-dd)
    names : list[str] # people to remind
    recurring : str # must be 'daily', 'weekly', or 'monthly', other values will be interpreted as 'off'
    content : str # what to remind the person of (copied from the task by default)
    task_id : str | None # [optional] the doc_id for the corresponding task

    recurring_options = ("daily", "weekly", "monthly", "yearly")

    def __init__(self, _reminder):
        self.doc_id = _reminder.doc_id
        self.time = _reminder['time']
        self.names = _reminder['names']
        self.recurring = _reminder['recurring']
        self.content = _reminder['content']
        self.task_id = _reminder['task_id'] if 'task_id' in _reminder else None
    
    def __str__(self):
        timestamp = timestamp_from_string(self.time)
        _str = f"**[{self.doc_id}]** {self.content} [<t:{timestamp}:R>]"
        if self.recurring in Reminder.recurring_options:
            _str += f" *(recurring {self.recurring})*"
        if self.task_id:
            _str += f" *(see task [{self.task_id}])*"
        return _str

    @classmethod
    def from_id(cls, reminder_id:int) -> Reminder:
        _reminder = cls.table.get(doc_id=reminder_id)
        if _reminder:
            return cls(_reminder)
        else:
            return None
    
    @classmethod
    def new_reminder(cls, time:str, names:list[str], recurring:str, content:str, task_id:str) -> Reminder:
        names = [format_name(name) for name in names if name]
        if task_id: # if a task is provided but not other essetial data, it is inferred from the task:
            task = Task.from_id(task_id)
            if not task:
                raise ToDoException(f"There is no task with id `[{task_id}]`...")
            if not time and task.deadline:
                time = f"{task.deadline} 10:00"
            if not task.name in names:
                names = [task.name, *names]
            if not content:
                content = task.content
        if time:
            time = datetime_from_string(time, format=TIME_FMT)
        for name in names:
            person = Person.from_name(name)
            if name and not person:
                raise ToDoException(f"Cannot generate reminder for person `{name}` as this name is not recognized.")
        if recurring:
            recurring = recurring.lower()
            if recurring not in Reminder.recurring_options:
                raise ToDoException(f"The value for `recurring` must be 'daily', 'weekly', 'monthly' or 'yearly' (leave empty for non-recurring).")
        else:
            recurring = 'off'
        if not (time and names and content):
            raise ToDoException(f"Either a time and content or a task (with deadline) must be provided to make a reminder.")
        _reminder = {
            'time': time,
            'names': names,
            'content': content,
            'recurring': recurring
        }
        if task_id:
            _reminder['task_id'] = task_id
        reminder_id = Reminder.table.insert(_reminder)
        return Reminder.from_id(reminder_id)

    @classmethod
    def remove_reminder(cls, reminder_id:int) -> Reminder:
        reminder = cls.from_id(reminder_id)
        if reminder:
            Reminder.table.remove(doc_ids=[reminder_id])
        return reminder

    @classmethod
    def update_reminders(cls):
        """ This function checks if any reminders have gone off, returns them,
        and either removes them from the database or resets their timer. """
        reminders = [cls(_reminder) for _reminder in cls.table.all()]
        reminders_to_show = []
        dt_now = datetime.datetime.now(pytz.timezone("Europe/Brussels"))
        now = dt_now.strftime(TIME_FMT)
        for reminder in reminders:
            if reminder.time < now:
                reminders_to_show.append(reminder)

                next_time = datetime_from_string(reminder.time)
                if reminder.recurring == 'daily':
                    while next_time < dt_now:
                        next_time += datetime.timedelta(days=1)
                elif reminder.recurring == 'weekly':
                    while next_time < dt_now:
                        next_time += datetime.timedelta(days=7)
                elif reminder.recurring == 'monthly':
                    while next_time < dt_now:
                        next_time += datetime.timedelta(days=1)
                elif reminder.recurring == 'yearly':
                    while next_time < dt_now:
                        next_time += datetime.timedelta(days=1)
                else:
                    # this reminder isn't recurring, it can just be deleted
                    cls.remove_reminder(reminder.doc_id)
                    continue
                 
                reminder.set_new_time(next_time.strftime(TIME_FMT))

        return reminders_to_show
                
    def set_new_time(self, time:str):
        time = datetime_from_string(time, TIME_FMT)
        self.time = time
        self.table.update({'time': time}, doc_ids=[self.doc_id])