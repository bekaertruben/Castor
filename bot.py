import discord
from discord import Option
from discord.ext import tasks
import asyncio

import todos
from todos import ToDoException

from functools import wraps
import os

TOKEN = os.environ['TOKEN']

todo_commands = discord.SlashCommandGroup("todo", "Commands to manage to-do lists")
reminder_commands = discord.SlashCommandGroup("reminder", "Commands to manage reminders")

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents)


GREEN = 0x7bb586
BROWN = 0x6a4441
RED   = 0xd34322


def catch_errors(command):
    """ This ensures errors are caught and reported to the user """
    @wraps(command)
    async def wrapper(ctx, *args, **kwargs):
        try:
            await command(ctx, *args, **kwargs)
        except ToDoException as e:
            embed = discord.Embed(title="Error", description=f"❌ {e.msg}", color=RED)
            await ctx.respond(embed=embed)
        except Exception as e:
            embed = discord.Embed(title="Error", description=f"❌ Command failed for unknown reason.", color=RED)
            await ctx.respond(embed=embed)
            raise e
    return wrapper


def parse_person(ctx, name:str):
    if name:
        person = todos.Person.from_name(name)
        if not person:
            raise ToDoException(f"No person with name `{name}` is known. Add them using `/todo newperson`.")
    else:
        person = todos.Person.from_id(str(ctx.author.id))
        if not person:
            raise ToDoException(f"You are not yet known to the system. Use `/todo newperson` to get started.")
    return person


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    update_reminders.start()


@todo_commands.command(name="newperson", description="Initializes a person into the to-do system")
@catch_errors
async def todo_newperson(ctx,
                    name: Option(str, "Enter name with which to refer to the user", required = True),
                    beautiful_name: Option(str, "This is the name which will be used in printing the to-do list", required = True),
                    id:   Option(str, "The user id (leave empty to add yourself)", required = False, default="")
                    ):
    if not id:
        id = str(ctx.author.id)
        if existing_person:=todos.Person.from_id(id):
            raise ToDoException(f"Your id (`{id}`) is already known under the name {existing_person.beautiful_name} (`{existing_person.name}`),\
                                    please provide a specific id for another person.")
    person = todos.Person.new_person(name, beautiful_name, id)
    embed = discord.Embed(title="Created user", description=f"✅ Successfully initialized user {person.beautiful_name} (<@{person.id}>)\
                            \nto refer to this user in commands, use `{person.name}`", color=GREEN)
    await ctx.respond(embed=embed)


@todo_commands.command(name="add", description="Adds a task to someone's to-do list")
@catch_errors
async def todo_add(ctx,
                    task: Option(str, "The task to add to the to-do list", required = True),
                    name: Option(str, "The user whose list you want to add to (leave empty for your own list)", required = False, default=""),
                    deadline: Option(str, "The task's deadline (leave empty if there is none)", required = False, default="")
                    ):
    person = parse_person(ctx, name)
    task = person.add_task(task, deadline)
    embed = discord.Embed(title="Added task", description=f"✅ Successfully added the following task for **{person.beautiful_name}**:\
                            \n---\n{task}", color=GREEN)
    await ctx.respond(embed=embed)


@todo_commands.command(name="remove", description="Marks a task as completed")
@catch_errors
async def todo_remove(ctx,
                    task_id: Option(int, "The numerical task id to remove", required = True),
                    ):
    task = todos.Task.remove_task(task_id)
    if not task:
        raise ToDoException(f"There is no task with id `{task_id}`.")
    person = todos.Person.from_name(task.name)
    embed = discord.Embed(title="Removed task", description=f"✅ Marked the following task as completed (owned by **{person.beautiful_name}**):\
                            \n---\n{task}", color=GREEN)
    await ctx.respond(embed=embed)
        

@todo_commands.command(name="list", description="Lists a person's to-do list")
@catch_errors
async def todo_list(ctx,
                    name: Option(str, "The user whose list you want to inspect (leave empty for your own list)", required = False, default=""),
                    ):
    person = parse_person(ctx, name)
    todo_list = person.todo_list()
    if not todo_list:
        todo_list = "Wow, such empty..."
    embed = discord.Embed(title=f"{person.beautiful_name}'s to-do's", description=todo_list, color=GREEN)
    await ctx.respond(embed=embed)


@reminder_commands.command(name="add", description="Schedules a reminder")
@catch_errors
async def reminder_add(ctx,
                    time: Option(str, "The date and/or time at which you want to set the reminder", required = False, default=None),
                    names: Option(str, "The user(s) who you want to remind of someting (comma-separated)", required = False, default=""),
                    recurring: Option(str, "How often to recur the reminder (leave empty for non-recurring)", required = False, choices=["daily", "weekly", "monthly", "yearly"]),
                    content: Option(str, "The content of the reminder (if empty, this is a copy of the task)", required = False, default=None),
                    task_id: Option(int, name="task", description="The task that is linked to the reminder", required = False, default=None),
                    ):
    names = names.split(",")
    if names == [""] and not task_id:
        person = parse_person(ctx, None)
        names = [person.name]
    reminder = todos.Reminder.new_reminder(time, names, recurring, content, task_id)
    people = [todos.Person.from_name(name).beautiful_name for name in reminder.names]
    people_str = ", ".join(people)
    embed = discord.Embed(title="Added task", description=f"✅ Successfully created the following reminder for **{people_str}** :\
                            \n---\n{reminder}", color=GREEN)
    await ctx.respond(embed=embed)


@reminder_commands.command(name="remove", description="Deletes a remider")
@catch_errors
async def reminder_remove(ctx,
                    reminder_id: Option(int, "The numerical reminder id to remove", required = True),
                    ):
    reminder = todos.Reminder.remove_reminder(reminder_id)
    if not reminder:
        raise ToDoException(f"There is no reminder with id `{reminder_id}`.")
    people = [todos.Person.from_name(name).beautiful_name for name in reminder.names]
    people_str = ", ".join(people)
    embed = discord.Embed(title="Removed task", description=f"✅ Removed the following reminder for **{people_str}**:\
                            \n---\n{reminder}", color=GREEN)
    await ctx.respond(embed=embed)


@reminder_commands.command(name="list", description="Lists a person's to-do list")
@catch_errors
async def reminder_list(ctx,
                    name: Option(str, "The user whose list you want to inspect (leave empty for your own list)", required = False, default=""),
                    ):
    person = parse_person(ctx, name)
    reminder_list = person.reminder_list()
    if not reminder_list:
        reminder_list = "Wow, such empty..."
    embed = discord.Embed(title=f"{person.beautiful_name}'s reminders (some may be shared with other people)", description=reminder_list, color=GREEN)
    await ctx.respond(embed=embed)



@tasks.loop(seconds=60)
async def update_reminders():
    reminders_to_show = todos.Reminder.update_reminders()
    for reminder in reminders_to_show:
        embed = discord.Embed(title="Reminder", description=str(reminder), color=BROWN)
        for name in reminder.names:
            person = todos.Person.from_name(name)
            user = await bot.fetch_user(person.id)
            await user.send(embed=embed)



bot.add_application_command(todo_commands)
bot.add_application_command(reminder_commands)
bot.run(TOKEN)