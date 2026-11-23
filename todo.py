
import os
import sys
import shutil

# PART 1 - SETTINGS

'''This is the file where tasks are stored (next to this program)'''
DATA_FILE = os.environ.get("TODO_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "todolist.dat")

'''This is the first line of the file. It remembers the next free ID.'''
HEADER = "#NEXT_ID="                  

'''Only these commands are allowed. The rest is ignored, but preserved in the file.'''
STATUSES = ("todo", "done")           
PRIORITIES = ("low", "med", "high")   # the only allowed priorities

'''Exit codes: 0 = success, 1 = user error, 2 = file problem'''
EXIT_OK, EXIT_USER_ERROR, EXIT_FILE_PROBLEM = 0, 1, 2

'''Colors only when printing to a real terminal.'''
if os.name == "nt":
    os.system("")                     # switches on color support in Windows terminals
USE_COLOR = "FORCE_COLOR" in os.environ or (
    sys.stdout.isatty() and "NO_COLOR" not in os.environ)


class UserError(Exception):
    '''The person typed something wrong (bad ID, empty text...). -> exit code 1'''


class FileProblem(Exception):
    '''The data file cannot be read or written. -> exit code 2'''

# PART 2 - PRETTY PRINTING HELPERS

DIM, BOLD, RED, GREEN, YELLOW, BLUE, CYAN, PINK = "2", "1", "1;31", "32", "33", "34", "1;36", "1;35"


def color(text, style):
    '''Wrap text in a color code (does nothing if colors are off).'''
    return f"\033[{style}m{text}\033[0m" if USE_COLOR else text


def ok(message):
    print(color("  ✓ ", GREEN) + message)


def warn(message):
    print(color("  ⚠ ", YELLOW) + message, file=sys.stderr)


def fail(message):
    print(color("  ✗ ", RED) + message, file=sys.stderr)


def banner(title):
    '''A little box with a centered title.'''
    width = 40
    print()
    print(color("╭" + "─" * width + "╮", CYAN))
    print(color("│", CYAN) + color(title.center(width), CYAN) + color("│", CYAN))
    print(color("╰" + "─" * width + "╯", CYAN))


def progress_bar(done, total, size=20):
    '''Example:  ████████░░░░░░░░░░░░ 40%'''
    percent = 100 * done // total if total else 0
    filled = round(size * done / total) if total else 0
    return color("█" * filled, GREEN) + color("░" * (size - filled), DIM) + f" {percent}%"


# PART 3 - THE FILE (loading, checking for tampering, saving)

def read_task(line):
    '''This checks ONE line against the format. This is the tampering detector.'''
    parts = line.split("|", 3)                       # 4 pieces max, so text may contain "|"
    if len(parts) != 4:
        return None, "it needs 4 parts separated by |"
    id_text, status, priority, text = parts
    if not (id_text.isascii() and id_text.isdigit()):
        return None, "the ID is not a number"
    if id_text != str(int(id_text)) or int(id_text) < 1:
        return None, "the ID must be 1 or higher"
    if status not in STATUSES:
        return None, f"unknown status '{status}'"
    if priority not in PRIORITIES:
        return None, f"unknown priority '{priority}'"
    if text.strip() == "":
        return None, "the task text is empty"
    return {"id": int(id_text), "status": status, "priority": priority, "text": text}, None


def leading_number(line):
    '''Pull a number from the start of a bad line, so we never reuse that ID.'''
    digits = ""
    for character in line.lstrip():
        if character.isascii() and character.isdigit():
            digits += character
        else:
            break
    return int(digits) if digits else 0


def load_file():
    '''Read the file. Returns the program's data (a dictionary).'''
    data = {"items": [], "next_id": 1, "warnings": [], "changed": False}
    if not os.path.exists(DATA_FILE):
        return data                                   # first run: nothing saved yet

    try:
        with open(DATA_FILE, encoding="utf-8", newline="") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as problem:
        raise FileProblem(f"Cannot read {DATA_FILE}: {problem}")

    lines = content.split("\n")
    if lines[-1] == "":
        lines.pop()                                    # ignore the final newline
    if not lines:
        return data                                    # empty file is fine

    # Line 1 should be the header with the ID counter.
    declared_next_id = None
    first_line_number = 1
    if lines[0].startswith(HEADER):
        number = lines[0][len(HEADER):]
        if number.isascii() and number.isdigit() and int(number) >= 1:
            declared_next_id = int(number)
            lines = lines[1:]
            first_line_number = 2

    # Check every other line.
    seen_ids = set()
    highest_id = 0
    for line_number, line in enumerate(lines, start=first_line_number):
        task, reason = read_task(line)
        if task is not None and task["id"] in seen_ids:
            task, reason = None, f"ID {task['id']} appears twice"
        if task is None:                               # TAMPERING: report, ignore, keep
            data["items"].append(line)
            data["warnings"].append(f"Line {line_number} ignored: {reason}. It was kept untouched.")
            highest_id = max(highest_id, leading_number(line))
        else:
            seen_ids.add(task["id"])
            data["items"].append(task)
            highest_id = max(highest_id, task["id"])

    # Decide the next free ID. It must be higher than every ID we have ever seen.
    safe_minimum = highest_id + 1
    if declared_next_id is None:
        data["warnings"].append("The #NEXT_ID header is missing or broken. It was rebuilt.")
        data["next_id"] = safe_minimum
    elif declared_next_id < safe_minimum:
        data["warnings"].append(f"The #NEXT_ID header ({declared_next_id}) was too low. Raised to {safe_minimum}.")
        data["next_id"] = safe_minimum
    else:
        data["next_id"] = declared_next_id
    return data


def save_file(data):
    '''Write everything back. Bad lines are written exactly as they were.'''
    lines = [HEADER + str(data["next_id"])]
    for item in data["items"]:
        if isinstance(item, dict):
            lines.append(f'{item["id"]}|{item["status"]}|{item["priority"]}|{item["text"]}')
        else:
            lines.append(item)                         # a bad line: preserved

    temp_name = DATA_FILE + ".tmp"                     # write to a temp file first, so a
    try:                                               # crash can't ruin the real file
        with open(temp_name, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(temp_name, DATA_FILE)
    except OSError as problem:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise FileProblem(f"Cannot write {DATA_FILE}: {problem}")

# PART 4 - SHOWING THE LIST

def all_tasks(data):
    return [item for item in data["items"] if isinstance(item, dict)]


def draw_table(tasks):
    '''Draw a table of tasks, with colors and borders.'''
    width = min(shutil.get_terminal_size((80, 20)).columns, 78)
    longest = max(len(t["text"]) for t in tasks)
    text_w = max(4, min(longest, max(10, width - 22)))      # width of the TASK column

    def rule(left, mid, right):
        return color(left + "─" * 6 + mid + "─" * 3 + mid + "─" * 6 + mid + "─" * (text_w + 2) + right, DIM)

    bar = color("│", DIM)

    def row(id_cell, status_cell, priority_cell, text_cell):
        return f"{bar} {id_cell} {bar} {status_cell} {bar} {priority_cell} {bar} {text_cell} {bar}"

    print(rule("┌", "┬", "┐"))
    print(row(color("  ID", BOLD), " ", color("PRI ", BOLD), color("TASK".ljust(text_w), BOLD)))
    print(rule("├", "┼", "┤"))

    # Open tasks first (high priority on top), finished tasks at the bottom.
    rank = {"high": 0, "med": 1, "low": 2}
    for t in sorted(tasks, key=lambda t: (t["status"] == "done", rank[t["priority"]], t["id"])):
        text = t["text"] if len(t["text"]) <= text_w else t["text"][:text_w - 1] + "…"
        id_cell = str(t["id"]).rjust(4)
        label = {"low": "LOW ", "med": "MED ", "high": "HIGH"}[t["priority"]]
        if t["status"] == "done":
            print(row(color(id_cell, DIM), color("✓", GREEN), color(label, DIM), color(text.ljust(text_w), "2;32")))
        else:
            label_color = {"low": BLUE, "med": YELLOW, "high": RED}[t["priority"]]
            print(row(id_cell, "○", color(label, label_color), text.ljust(text_w)))
    print(rule("└", "┴", "┘"))


def show_list(data, which="all"):
    banner("T O D O   L I S T")
    everything = all_tasks(data)
    wanted = {"all": ("todo", "done"), "open": ("todo",), "done": ("done",)}[which]
    shown = [t for t in everything if t["status"] in wanted]
    if shown:
        draw_table(shown)
    else:
        print(color("\n  Nothing here yet.  Try:  add Buy milk\n", DIM))
    finished = sum(t["status"] == "done" for t in everything)
    print(f"  {progress_bar(finished, len(everything))}   {finished} of {len(everything)} done\n")


# PART 5 - THE COMMANDS

def find_task(data, args):
    '''Turn a typed number into the task with that ID. Complains if it doesn't exist.'''
    if not args:
        raise UserError("Give a task number, for example:  done 3")
    if not (args[0].isascii() and args[0].isdigit()):
        raise UserError(f"'{args[0]}' is not a number.")
    for task in all_tasks(data):
        if task["id"] == int(args[0]):
            return task
    raise UserError(f"There is no task #{args[0]}.")


def clean_text(words):
    return " ".join(" ".join(words).split())          # one line, single spaces


def cmd_add(args, data):
    priority = "med"
    if "-p" in args:                                   # e.g.  add Buy milk -p high
        position = args.index("-p")
        if position + 1 >= len(args) or args[position + 1].lower() not in PRIORITIES:
            raise UserError("-p must be followed by low, med or high.")
        priority = args[position + 1].lower()
        args = args[:position] + args[position + 2:]
    text = clean_text(args)
    if text == "":
        raise UserError("Write something to add, for example:  add Buy milk")
    task = {"id": data["next_id"], "status": "todo", "priority": priority, "text": text}
    data["next_id"] += 1                               # the counter only ever goes UP
    data["items"].append(task)
    data["changed"] = True
    ok(f"Added task #{task['id']}: {text}")


def cmd_done(args, data):
    task = find_task(data, args)
    task["status"] = "done"
    data["changed"] = True
    ok(f"Task #{task['id']} is done. Nice!")


def cmd_undo(args, data):
    task = find_task(data, args)
    task["status"] = "todo"
    data["changed"] = True
    ok(f"Task #{task['id']} is open again.")


def cmd_edit(args, data):
    task = find_task(data, args)
    text = clean_text(args[1:])
    if text == "":
        raise UserError("Write the new text, for example:  edit 3 Buy oat milk")
    task["text"] = text
    data["changed"] = True
    ok(f"Task #{task['id']} updated.")


def cmd_delete(args, data):
    task = find_task(data, args)
    data["items"] = [item for item in data["items"] if item is not task]
    data["changed"] = True                             # note: next_id is NOT changed
    ok(f"Task #{task['id']} deleted. (Its number will never be reused.)")


def cmd_list(args, data):
    which = args[0].lower() if args else "all"
    if which not in ("all", "open", "done"):
        raise UserError("Use:  list, list open  or  list done")
    show_list(data, which)


def cmd_stats(args, data):
    tasks = all_tasks(data)
    finished = sum(t["status"] == "done" for t in tasks)
    banner("S T A T S")
    print(f"\n  Total tasks : {len(tasks)}")
    print(f"  Finished    : {finished}")
    print(f"  Progress    : {progress_bar(finished, len(tasks))}")
    for p in ("high", "med", "low"):
        count = sum(t["status"] == "todo" and t["priority"] == p for t in tasks)
        print(f"  Open {p:<4}   : {count}")
    print(f"  Next ID     : #{data['next_id']}\n")


def cmd_check(args, data):
    banner("F I L E   C H E C K")
    if data["warnings"]:
        print()
        for message in data["warnings"]:
            warn(message)
        print()
        return EXIT_FILE_PROBLEM
    ok("The file is clean. No tampering found.")
    print()
    return EXIT_OK


def cmd_help(args, data):
    banner("H E L P")
    rows = [("add TEXT [-p low|med|high]", "add a task"),
            ("list [open|done]", "show your tasks"),
            ("done ID", "mark a task finished"),
            ("undo ID", "mark it not finished"),
            ("edit ID NEW TEXT", "change a task's text"),
            ("delete ID", "remove a task"),
            ("stats", "show a summary"),
            ("check", "look for tampering in the file"),
            ("quit", "save and leave")]
    print()
    for command, meaning in rows:
        print("  " + color(command.ljust(28), PINK) + meaning)
    print()


COMMANDS = {"add": cmd_add, "list": cmd_list, "done": cmd_done, "undo": cmd_undo,
            "edit": cmd_edit, "delete": cmd_delete, "rm": cmd_delete,
            "stats": cmd_stats, "check": cmd_check, "help": cmd_help}
CHANGING_COMMANDS = ("add", "done", "undo", "edit", "delete", "rm")


def run_command(words, data):
    '''Find the command and run it. Raises UserError if something is wrong.'''
    name = words[0].lower()
    if name not in COMMANDS:
        raise UserError(f"Unknown command '{words[0]}'. Type  help  to see the commands.")
    return COMMANDS[name](words[1:], data) or EXIT_OK


# PART 6 - THE TWO WAYS TO RUN THE PROGRAM

def interactive(data):
    '''The pretty screen: type commands one after another.'''
    show_list(data)
    print(color("  Type help for commands, quit to save and leave.\n", DIM))
    while True:
        try:
            line = input(color("todo ❯ ", PINK))
        except (EOFError, KeyboardInterrupt):          # Ctrl+D or Ctrl+C
            print()
            break
        words = line.split()
        if not words:
            continue
        if words[0].lower() in ("quit", "exit", "q"):
            break
        try:
            run_command(words, data)
            if words[0].lower() in CHANGING_COMMANDS:
                show_list(data)                        # redraw after every change
        except UserError as mistake:
            fail(str(mistake))
    print(color("  Saved. Goodbye!\n", DIM))
    return EXIT_OK


def main():
    '''Load file -> report tampering -> run command -> save -> return exit code.'''
    words = sys.argv[1:]

    try:
        data = load_file()
    except FileProblem as problem:
        fail(str(problem))
        return EXIT_FILE_PROBLEM

    # Tell the user if someone edited the file by hand.
    if data["warnings"] and not (words and words[0].lower() == "check"):
        print(color("\n  TAMPERING DETECTED - the file was edited outside this program:", YELLOW), file=sys.stderr)
        for message in data["warnings"]:
            warn(message)

    exit_code = EXIT_OK
    if words:
        try:
            exit_code = run_command(words, data)
        except UserError as mistake:
            fail(str(mistake))
            exit_code = EXIT_USER_ERROR
    else:
        exit_code = interactive(data)

    if data["changed"]:                                # save when the program ends
        try:
            save_file(data)
        except FileProblem as problem:
            fail(str(problem))
            return EXIT_FILE_PROBLEM
    return exit_code


if __name__ == "__main__":
    sys.exit(main())