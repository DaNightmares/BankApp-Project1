import ctypes
import math
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

# ---------------------------------------------------------------------------
# ctypes declarations (must match bank_wrapper.cpp)
# ---------------------------------------------------------------------------

BANK_OK = 0
BANK_ERR_BAD_ARGUMENT = 1
BANK_ERR_INVALID_AMOUNT = 2
BANK_ERR_ACCOUNT_NOT_FOUND = 3
BANK_ERR_INSUFFICIENT_FUNDS = 4
BANK_ERR_DUPLICATE_ACCOUNT = 5
BANK_ERR_INVALID_RECORD = 6
BANK_ERR_FILE = 7
BANK_ERR_MEMORY = 8
BANK_ERR_UNKNOWN = 99

BANK_TEXT_SIZE = 256


class ClientInfo(ctypes.Structure):
    """Mirror of the ClientInfo struct in bank_wrapper.cpp."""

    _fields_ = [
        ("client_name", ctypes.c_char * BANK_TEXT_SIZE),
        ("ssn", ctypes.c_char * BANK_TEXT_SIZE),
        ("bank_account_number", ctypes.c_char * BANK_TEXT_SIZE),
        ("balance", ctypes.c_double),
    ]


def library_path():
    """The shared library is expected next to this script."""
    folder = os.path.dirname(os.path.abspath(__file__))
    if sys.platform == "win32":
        name = "bank.dll"
    elif sys.platform == "darwin":
        name = "libbank.dylib"
    else:
        name = "libbank.so"
    return os.path.join(folder, name)


def load_library():
    """Load the C++ library and declare every function's argument and return types.

    Declaring the types matters: without them ctypes assumes plain ints, which
    cuts 64-bit pointers in half and passes doubles incorrectly.
    """
    lib = ctypes.CDLL(library_path())

    lib.bank_create.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    lib.bank_create.restype = ctypes.c_void_p

    lib.bank_destroy.argtypes = [ctypes.c_void_p]
    lib.bank_destroy.restype = None

    lib.bank_get_num_clients.argtypes = [ctypes.c_void_p]
    lib.bank_get_num_clients.restype = ctypes.c_int

    lib.bank_get_client_at.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ClientInfo)]
    lib.bank_get_client_at.restype = ctypes.c_int

    lib.bank_find_client.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ClientInfo)]
    lib.bank_find_client.restype = ctypes.c_int

    lib.bank_deposit.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_double,
                                 ctypes.POINTER(ctypes.c_double)]
    lib.bank_deposit.restype = ctypes.c_int

    lib.bank_withdraw.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_double,
                                  ctypes.POINTER(ctypes.c_double)]
    lib.bank_withdraw.restype = ctypes.c_int

    lib.bank_add_client.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
                                    ctypes.c_char_p, ctypes.c_double]
    lib.bank_add_client.restype = ctypes.c_int

    lib.bank_save.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.bank_save.restype = ctypes.c_int

    return lib


# ---------------------------------------------------------------------------
# Small helpers (display and input only, no banking rules)
# ---------------------------------------------------------------------------

def to_c(text):
    """Python str -> bytes for a const char* argument."""
    return text.encode("utf-8")


def from_c(raw):
    """bytes from a C char buffer -> Python str."""
    return raw.decode("utf-8", errors="replace")


def path_to_c(path):
    """File path -> bytes in the encoding the C++ file streams expect."""
    if sys.platform == "win32":
        return path.encode("mbcs")
    return os.fsencode(path)


def mask_ssn(ssn):
    """Hide everything except the last four characters: 000-00-1234 -> ***-**-1234."""
    total = sum(ch.isalnum() for ch in ssn)
    to_hide = total - 4 if total > 4 else total
    masked = []
    for ch in ssn:
        if ch.isalnum() and to_hide > 0:
            masked.append("*")
            to_hide -= 1
        else:
            masked.append(ch)
    return "".join(masked)


def format_money(amount):
    return f"${amount:,.2f}"


def parse_number(text, field_name):
    """Turn entry text into a float, or raise ValueError with a readable message."""
    text = text.strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{field_name} must be a number, for example 250.00.") from None
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be a normal number, for example 250.00.")
    return value


# ---------------------------------------------------------------------------
# The application
# ---------------------------------------------------------------------------

class BankApp:
    SUCCESS_COLOR = "#1b6e2d"
    ERROR_COLOR = "#b00020"
    NEUTRAL_COLOR = "#333333"

    def __init__(self, root):
        self.root = root
        self.lib = load_library()   # raises OSError if the library is missing
        self.bank = None            # handle to the C++ Bank object (None until a file is loaded)
        self.file_name = ""         # name of the loaded file, for display
        self.unsaved_changes = False
        self.shown_account = None   # account currently displayed in the Find section
        self.dark_mode = False
        self.style = ttk.Style(self.root)

        self._build_widgets()
        self.apply_theme()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # Any unexpected Python error in a button handler is shown, not fatal.
        self.root.report_callback_exception = self._on_unexpected_error
        self._set_status("Start by loading a client file.", self.NEUTRAL_COLOR)

    # ----- layout ----------------------------------------------------------

    def _build_widgets(self):
        root = self.root
        root.title("Bank Client Manager")
        root.minsize(900, 600)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.bold_font = tkfont.nametofont("TkDefaultFont").copy()
        self.bold_font.configure(weight="bold")

        main = ttk.Frame(root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1, uniform="half")
        main.columnconfigure(1, weight=1, uniform="half")
        main.rowconfigure(2, weight=1)

        # 1. Client file
        file_frame = ttk.LabelFrame(main, text="1. Client file", padding=10)
        file_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        file_frame.columnconfigure(2, weight=1)
        ttk.Button(file_frame, text="Load client file...", command=self.load_file).grid(
            row=0, column=0, padx=(0, 8))
        ttk.Button(file_frame, text="Save data...", command=self.save_file).grid(
            row=0, column=1, padx=(0, 12))
        self.file_label = ttk.Label(file_frame, text="No file loaded")
        self.file_label.grid(row=0, column=2, sticky="w")
        self.theme_button = ttk.Button(
            file_frame, text="🌙 Dark mode", command=self.toggle_theme)
        self.theme_button.grid(row=0, column=3, sticky="e", padx=(8, 0))

        # 2. Find client
        find_frame = ttk.LabelFrame(main, text="2. Find client", padding=10)
        find_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5), pady=(0, 10))
        find_frame.columnconfigure(1, weight=1)
        self.find_account = self._field(find_frame, 0, "Account number")
        self.find_account.bind("<Return>", lambda event: self.find_client())
        ttk.Button(find_frame, text="Find", command=self.find_client).grid(
            row=1, column=1, sticky="w", pady=(6, 8))
        self.result_name = self._result_row(find_frame, 2, "Client name")
        self.result_ssn = self._result_row(find_frame, 3, "SSN")
        self.result_account = self._result_row(find_frame, 4, "Account number")
        self.result_balance = self._result_row(find_frame, 5, "Balance")

        # 3. Deposit / withdraw
        money_frame = ttk.LabelFrame(main, text="3. Deposit or withdraw", padding=10)
        money_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 0), pady=(0, 10))
        money_frame.columnconfigure(1, weight=1)
        self.money_account = self._field(money_frame, 0, "Account number")
        self.money_amount = self._field(money_frame, 1, "Amount ($)")
        buttons = ttk.Frame(money_frame)
        buttons.grid(row=2, column=1, sticky="w", pady=(6, 8))
        ttk.Button(buttons, text="Deposit", command=self.deposit).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Withdraw", command=self.withdraw).grid(row=0, column=1)
        self.money_result = self._result_row(money_frame, 3, "Updated balance")

        # 4. Add new client
        add_frame = ttk.LabelFrame(main, text="4. Add new client", padding=10)
        add_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 5), pady=(0, 10))
        add_frame.columnconfigure(1, weight=1)
        self.add_name = self._field(add_frame, 0, "Client name")
        self.add_ssn = self._field(add_frame, 1, "SSN")
        self.add_account = self._field(add_frame, 2, "Account number")
        self.add_balance = self._field(add_frame, 3, "Opening balance ($)")
        ttk.Button(add_frame, text="Add client", command=self.add_client).grid(
            row=4, column=1, sticky="w", pady=(6, 0))

        # All clients (read-only list)
        list_frame = ttk.LabelFrame(main, text="All clients", padding=10)
        list_frame.grid(row=2, column=1, sticky="nsew", padx=(5, 0), pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        columns = ("name", "ssn", "account", "balance")
        self.client_list = ttk.Treeview(list_frame, columns=columns, show="headings", height=7)
        for column, heading, width, anchor in (
            ("name", "Client name", 140, "w"),
            ("ssn", "SSN", 95, "w"),
            ("account", "Account", 85, "w"),
            ("balance", "Balance", 95, "e"),
        ):
            self.client_list.heading(column, text=heading, anchor=anchor)
            self.client_list.column(column, width=width, anchor=anchor)
        self.client_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.client_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.client_list.configure(yscrollcommand=scrollbar.set)

        # Status line: feedback for every operation
        self.status_label = tk.Label(main, text="", anchor="w", justify="left",
                                     relief="groove", padx=8, pady=6, wraplength=860)
        self.status_label.grid(row=3, column=0, columnspan=2, sticky="ew")

    def toggle_theme(self):
        """Switch between light and dark appearance without changing bank data."""
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def apply_theme(self):
        """Apply the selected colors to the Tkinter interface."""
        if self.dark_mode:
            colors = {
                "window": "#111827",
                "panel": "#1F2937",
                "field": "#111827",
                "text": "#F3F4F6",
                "muted": "#D1D5DB",
                "border": "#374151",
                "accent": "#10B981",
                "accent_active": "#059669",
                "select_bg": "#065F46",
                "select_fg": "#FFFFFF",
                "success": "#34D399",
                "error": "#F87171",
            }
            self.theme_button.configure(text="☀ Light mode")
        else:
            colors = {
                "window": "#F3F4F6",
                "panel": "#FFFFFF",
                "field": "#FFFFFF",
                "text": "#111827",
                "muted": "#4B5563",
                "border": "#D1D5DB",
                "accent": "#047857",
                "accent_active": "#065F46",
                "select_bg": "#D1FAE5",
                "select_fg": "#111827",
                "success": self.SUCCESS_COLOR,
                "error": self.ERROR_COLOR,
            }
            self.theme_button.configure(text="🌙 Dark mode")

        # The "clam" theme allows Tkinter's ttk widgets to be colored consistently.
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(bg=colors["window"])
        self.style.configure("TFrame", background=colors["window"])
        self.style.configure(
            "TLabel", background=colors["window"], foreground=colors["text"])
        self.style.configure(
            "TLabelframe", background=colors["window"], foreground=colors["text"],
            bordercolor=colors["border"])
        self.style.configure(
            "TLabelframe.Label", background=colors["window"],
            foreground=colors["text"])
        self.style.configure(
            "TButton", background=colors["panel"], foreground=colors["text"],
            bordercolor=colors["border"], padding=(10, 5))
        self.style.map(
            "TButton",
            background=[("active", colors["accent"]), ("pressed", colors["accent_active"])],
            foreground=[("active", "#FFFFFF"), ("pressed", "#FFFFFF")])
        self.style.configure(
            "TEntry", fieldbackground=colors["field"], foreground=colors["text"],
            insertcolor=colors["text"], bordercolor=colors["border"])
        self.style.configure(
            "Treeview", background=colors["panel"], fieldbackground=colors["panel"],
            foreground=colors["text"], rowheight=26, bordercolor=colors["border"])
        self.style.map(
            "Treeview",
            background=[("selected", colors["select_bg"])],
            foreground=[("selected", colors["select_fg"])])
        self.style.configure(
            "Treeview.Heading", background=colors["window"],
            foreground=colors["text"], relief="flat")
        self.style.map(
            "Treeview.Heading", background=[("active", colors["border"])])
        self.style.configure(
            "Vertical.TScrollbar", background=colors["panel"],
            troughcolor=colors["window"], bordercolor=colors["border"])

        self.status_label.configure(
            bg=colors["panel"], fg=colors["muted"],
            insertbackground=colors["text"])
        # Keep success/error status messages readable after a theme change.
        if self.status_label.cget("text").startswith("Error:"):
            self.status_label.configure(fg=colors["error"])
        elif any(word in self.status_label.cget("text").lower()
                 for word in ("loaded", "saved", "found", "deposited", "withdrew", "added")):
            self.status_label.configure(fg=colors["success"])
        else:
            self.status_label.configure(fg=colors["muted"])

    def _field(self, parent, row, label):
        """A labelled text entry. Returns the Entry widget."""
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        entry = ttk.Entry(parent)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        return entry

    def _result_row(self, parent, row, label):
        """A labelled read-only value. Returns the value Label."""
        ttk.Label(parent, text=label + ":").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        value = ttk.Label(parent, text="-", font=self.bold_font)
        value.grid(row=row, column=1, sticky="w", pady=2)
        return value

    # ----- feedback --------------------------------------------------------

    def _set_status(self, message, color):
        if self.dark_mode:
            if color == self.SUCCESS_COLOR:
                color = "#34D399"
            elif color == self.ERROR_COLOR:
                color = "#F87171"
            elif color == self.NEUTRAL_COLOR:
                color = "#D1D5DB"
        self.status_label.configure(text=message, fg=color)

    def show_success(self, message):
        self._set_status(message, self.SUCCESS_COLOR)

    def show_error(self, message):
        self._set_status("Error: " + message, self.ERROR_COLOR)
        messagebox.showerror("Bank Client Manager", message, parent=self.root)

    def _on_unexpected_error(self, exc_type, exc_value, exc_traceback):
        self.show_error(f"Unexpected problem: {exc_value}. Nothing was changed.")

    def _require_bank(self):
        if self.bank is None:
            self.show_error("Load a client file first, using the button at the top.")
            return False
        return True

    def _backend_message(self, status, account=""):
        """Readable text for a status code returned by the C++ library."""
        if status == BANK_ERR_ACCOUNT_NOT_FOUND:
            return (f"No client has account number \"{account}\". "
                    "Check the number and try again.")
        if status == BANK_ERR_INVALID_AMOUNT:
            return "Amount must be greater than 0."
        if status == BANK_ERR_INSUFFICIENT_FUNDS:
            return "The withdrawal is larger than the available balance."
        if status == BANK_ERR_DUPLICATE_ACCOUNT:
            return (f"Account number \"{account}\" already belongs to another client. "
                    "Choose a different account number.")
        if status == BANK_ERR_INVALID_RECORD:
            return "The backend rejected this client record. Check every field."
        if status == BANK_ERR_FILE:
            return "The file could not be opened or written."
        if status == BANK_ERR_MEMORY:
            return "The backend ran out of memory."
        return f"The backend reported an unexpected problem (code {status})."

    # ----- display ---------------------------------------------------------

    def _lookup(self, account):
        """Ask the backend for one client. Returns (status, ClientInfo)."""
        info = ClientInfo()
        status = self.lib.bank_find_client(self.bank, to_c(account), ctypes.byref(info))
        return status, info

    def _display_client(self, info):
        self.result_name.configure(text=from_c(info.client_name))
        self.result_ssn.configure(text=mask_ssn(from_c(info.ssn)))
        self.result_account.configure(text=from_c(info.bank_account_number))
        self.result_balance.configure(text=format_money(info.balance))
        self.shown_account = from_c(info.bank_account_number)

    def _clear_client(self):
        for label in (self.result_name, self.result_ssn, self.result_account, self.result_balance):
            label.configure(text="-")
        self.shown_account = None

    def _refresh(self):
        """Redraw the client list and the Find result from the backend's current state."""
        self.client_list.delete(*self.client_list.get_children())
        count = self.lib.bank_get_num_clients(self.bank) if self.bank is not None else 0
        self.file_label.configure(text=f"{self.file_name}  ({count} clients)")
        info = ClientInfo()
        for index in range(max(count, 0)):
            if self.lib.bank_get_client_at(self.bank, index, ctypes.byref(info)) == BANK_OK:
                self.client_list.insert("", "end", values=(
                    from_c(info.client_name),
                    mask_ssn(from_c(info.ssn)),
                    from_c(info.bank_account_number),
                    format_money(info.balance),
                ))
        if self.shown_account is not None:
            status, info = self._lookup(self.shown_account)
            if status == BANK_OK:
                self._display_client(info)
            else:
                self._clear_client()

    # ----- operations ------------------------------------------------------

    def load_file(self):
        if self.unsaved_changes and not messagebox.askyesno(
                "Bank Client Manager",
                "You have changes that are not saved. Load another file and lose them?",
                parent=self.root):
            return
        path = filedialog.askopenfilename(
            parent=self.root, title="Select a client file",
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            self._set_status("Load cancelled. Nothing was changed.", self.NEUTRAL_COLOR)
            return

        status = ctypes.c_int(BANK_ERR_UNKNOWN)
        handle = self.lib.bank_create(path_to_c(path), ctypes.byref(status))
        if not handle:
            self.show_error(f"Could not load \"{path}\". " + self._backend_message(status.value))
            return

        # Only replace the old bank once the new one loaded successfully.
        if self.bank is not None:
            self.lib.bank_destroy(self.bank)
        self.bank = handle
        self.file_name = os.path.basename(path)
        self.unsaved_changes = False
        self._clear_client()
        self.money_result.configure(text="-")
        self._refresh()

        count = self.lib.bank_get_num_clients(self.bank)
        name = os.path.basename(path)
        if count == 0:
            self.show_error(
                f"\"{name}\" was opened, but it has no valid client records. Each line must be: "
                "client_name,ssn,bank_account_number,balance. You can still add clients.")
        else:
            self.show_success(f"Loaded {count} clients from {name}.")

    def save_file(self):
        if not self._require_bank():
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save client data as", defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            self._set_status("Save cancelled. Nothing was written.", self.NEUTRAL_COLOR)
            return

        status = self.lib.bank_save(self.bank, path_to_c(path))
        if status != BANK_OK:
            self.show_error(f"Could not save to \"{path}\". " + self._backend_message(status))
            return
        self.unsaved_changes = False
        count = self.lib.bank_get_num_clients(self.bank)
        self.show_success(f"Saved {count} clients to {os.path.basename(path)}.")

    def find_client(self):
        if not self._require_bank():
            return
        account = self.find_account.get().strip()
        if not account:
            self.show_error("Enter an account number to search for.")
            return

        status, info = self._lookup(account)
        if status != BANK_OK:
            self._clear_client()
            self.show_error(self._backend_message(status, account))
            return
        self._display_client(info)
        self.show_success(f"Found account {account}: {from_c(info.client_name)}.")

    def deposit(self):
        self._transaction("deposit")

    def withdraw(self):
        self._transaction("withdraw")

    def _transaction(self, kind):
        if not self._require_bank():
            return
        account = self.money_account.get().strip()
        if not account:
            self.show_error("Enter the account number.")
            return
        try:
            amount = parse_number(self.money_amount.get(), "Amount")
        except ValueError as error:
            self.show_error(str(error))
            return
        if amount <= 0:
            self.show_error("Amount must be greater than 0.")
            return

        new_balance = ctypes.c_double(0.0)
        call = self.lib.bank_deposit if kind == "deposit" else self.lib.bank_withdraw
        status = call(self.bank, to_c(account), amount, ctypes.byref(new_balance))

        if status == BANK_ERR_INSUFFICIENT_FUNDS:
            lookup_status, info = self._lookup(account)
            available = format_money(info.balance) if lookup_status == BANK_OK else "the amount"
            self.show_error(
                f"Cannot withdraw {format_money(amount)} from account {account}: "
                f"only {available} is available. The balance was not changed.")
            return
        if status != BANK_OK:
            self.show_error(self._backend_message(status, account))
            return

        self.unsaved_changes = True
        self.money_result.configure(text=format_money(new_balance.value))
        self.money_amount.delete(0, "end")
        self._refresh()
        verb = "Deposited" if kind == "deposit" else "Withdrew"
        direction = "into" if kind == "deposit" else "from"
        self.show_success(
            f"{verb} {format_money(amount)} {direction} account {account}. "
            f"Updated balance: {format_money(new_balance.value)}.")

    def add_client(self):
        if not self._require_bank():
            return
        fields = (
            ("Client name", self.add_name.get().strip()),
            ("SSN", self.add_ssn.get().strip()),
            ("Account number", self.add_account.get().strip()),
        )
        for label, value in fields:
            if not value:
                self.show_error(f"{label} is required.")
                return
            if "," in value:
                self.show_error(f"{label} cannot contain a comma, because the file is comma-separated.")
                return
        name, ssn, account = (value for _, value in fields)
        try:
            balance = parse_number(self.add_balance.get(), "Opening balance")
        except ValueError as error:
            self.show_error(str(error))
            return
        if balance < 0:
            self.show_error("Opening balance cannot be negative.")
            return

        status = self.lib.bank_add_client(self.bank, to_c(name), to_c(ssn), to_c(account), balance)
        if status != BANK_OK:
            self.show_error(self._backend_message(status, account))
            return

        self.unsaved_changes = True
        for entry in (self.add_name, self.add_ssn, self.add_account, self.add_balance):
            entry.delete(0, "end")
        self._refresh()
        self.show_success(
            f"Added {name} with account {account} and opening balance {format_money(balance)}.")

    def on_close(self):
        if self.unsaved_changes and not messagebox.askyesno(
                "Bank Client Manager",
                "You have changes that are not saved. Close without saving?",
                parent=self.root):
            return
        if self.bank is not None:
            self.lib.bank_destroy(self.bank)   # release the C++ object
            self.bank = None
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        BankApp(root)
    except OSError as error:
        root.withdraw()
        messagebox.showerror(
            "Bank Client Manager",
            "The C++ library could not be loaded.\n\n"
            f"Expected file: {library_path()}\n\n"
            "Build it from bank.cpp and bank_wrapper.cpp, put it in the same folder as "
            f"bank_app.py, then start the program again.\n\nDetails: {error}")
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()

