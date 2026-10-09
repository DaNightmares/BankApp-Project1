#include "bank.h"

#include <cmath>
#include <cstddef>
#include <fstream>
#include <iomanip>
#include <stdexcept>

// ---------------------------------------------------------------------------
// File-local helpers
// ---------------------------------------------------------------------------
namespace {

// Remove leading/trailing spaces, tabs and line-ending characters.
// The '\r' matters when a CSV saved on Windows is read on Linux/macOS.
std::string trim(const std::string& s) {
    const char* whitespace = " \t\r\n";
    const std::size_t first = s.find_first_not_of(whitespace);
    if (first == std::string::npos) {
        return "";
    }
    const std::size_t last = s.find_last_not_of(whitespace);
    return s.substr(first, last - first + 1);
}

// A text field is usable if it is not empty and cannot break the CSV layout.
bool is_clean_field(const std::string& field) {
    return !field.empty() && field.find_first_of(",\r\n") == std::string::npos;
}

}  // namespace

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

int Bank::find_index(const std::string& bank_account_number) const {
    for (int i = 0; i < num_clients; ++i) {
        if (clients[i].bank_account_number == bank_account_number) {
            return i;
        }
    }
    return -1;
}

bool Bank::is_valid(const Client& c) {
    return is_clean_field(c.client_name) &&
           is_clean_field(c.ssn) &&
           is_clean_field(c.bank_account_number) &&
           std::isfinite(c.balance) &&
           c.balance >= 0.0;
}

// Turn one CSV line into a Client. Returns false for anything malformed:
// wrong number of fields, empty fields, or a balance that is not a number.
bool Bank::parse_line(const std::string& line, Client& out) {
    std::string fields[4];
    std::size_t start = 0;

    for (int i = 0; i < 4; ++i) {
        const std::size_t comma = line.find(',', start);
        if (i < 3) {
            if (comma == std::string::npos) {
                return false;  // too few fields
            }
            fields[i] = trim(line.substr(start, comma - start));
            start = comma + 1;
        } else {
            if (comma != std::string::npos) {
                return false;  // too many fields
            }
            fields[i] = trim(line.substr(start));
        }
    }

    double balance = 0.0;
    try {
        std::size_t used = 0;
        balance = std::stod(fields[3], &used);
        if (used != fields[3].size()) {
            return false;  // trailing junk such as "100abc"
        }
    } catch (const std::exception&) {
        return false;  // not a number at all (also skips a header row)
    }

    Client c;
    c.client_name = fields[0];
    c.ssn = fields[1];
    c.bank_account_number = fields[2];
    c.balance = balance;

    if (!is_valid(c)) {
        return false;
    }
    out = c;
    return true;
}

// ---------------------------------------------------------------------------
// Construction and file loading
// ---------------------------------------------------------------------------

Bank::Bank(const std::string& filename) : num_clients(0), clients(nullptr) {
    std::ifstream in(filename);
    if (!in) {
        return;  // no file yet: start as an empty bank
    }

    // Pass 1: count the lines that are valid records so we know how much to allocate.
    std::string line;
    Client temp;
    int capacity = 0;
    while (std::getline(in, line)) {
        if (parse_line(line, temp)) {
            ++capacity;
        }
    }
    if (capacity == 0) {
        return;
    }

    clients = new Client[capacity];

    // Pass 2: rewind and store the records. Duplicate account numbers are skipped.
    in.clear();
    in.seekg(0);
    while (num_clients < capacity && std::getline(in, line)) {
        if (parse_line(line, temp) && find_index(temp.bank_account_number) == -1) {
            clients[num_clients] = temp;
            ++num_clients;
        }
    }
}

// ---------------------------------------------------------------------------
// Rule of Three
// ---------------------------------------------------------------------------

Bank::~Bank() {
    delete[] clients;  // delete[] on nullptr is safe
}

Bank::Bank(const Bank& other) : num_clients(other.num_clients), clients(nullptr) {
    if (num_clients > 0) {
        clients = new Client[num_clients];
        for (int i = 0; i < num_clients; ++i) {
            clients[i] = other.clients[i];
        }
    }
}

Bank& Bank::operator=(const Bank& other) {
    if (this == &other) {
        return *this;  // self-assignment: nothing to do
    }

    // Build the new array first, so this object is untouched if allocation fails.
    Client* fresh = nullptr;
    if (other.num_clients > 0) {
        fresh = new Client[other.num_clients];
        for (int i = 0; i < other.num_clients; ++i) {
            fresh[i] = other.clients[i];
        }
    }

    delete[] clients;
    clients = fresh;
    num_clients = other.num_clients;
    return *this;
}

// ---------------------------------------------------------------------------
// Client access / search
// ---------------------------------------------------------------------------

const Client* Bank::get_clients_info() const {
    return clients;
}

int Bank::get_num_clients() const {
    return num_clients;
}

const Client* Bank::find_client(const std::string& bank_account_number) const {
    const int index = find_index(bank_account_number);
    return (index == -1) ? nullptr : &clients[index];
}

// ---------------------------------------------------------------------------
// Transactions
// ---------------------------------------------------------------------------

double Bank::deposit(const std::string& bank_account_number, double amount) {
    if (!std::isfinite(amount) || amount <= 0.0) {
        throw std::invalid_argument("Deposit amount must be greater than zero.");
    }
    const int index = find_index(bank_account_number);
    if (index == -1) {
        throw std::out_of_range("Account not found: " + bank_account_number);
    }

    clients[index].balance += amount;
    return clients[index].balance;
}

double Bank::withdraw(const std::string& bank_account_number, double amount) {
    if (!std::isfinite(amount) || amount <= 0.0) {
        throw std::invalid_argument("Withdrawal amount must be greater than zero.");
    }
    const int index = find_index(bank_account_number);
    if (index == -1) {
        throw std::out_of_range("Account not found: " + bank_account_number);
    }
    if (amount > clients[index].balance) {
        throw std::runtime_error("Insufficient funds.");
    }

    clients[index].balance -= amount;
    return clients[index].balance;
}

// ---------------------------------------------------------------------------
// Adding a client
// ---------------------------------------------------------------------------

bool Bank::add_new_client(const Client& new_client) {
    Client c;
    c.client_name = trim(new_client.client_name);
    c.ssn = trim(new_client.ssn);
    c.bank_account_number = trim(new_client.bank_account_number);
    c.balance = new_client.balance;

    if (!is_valid(c)) {
        return false;
    }
    if (find_index(c.bank_account_number) != -1) {
        return false;  // duplicate account number
    }

    // Resize: allocate a bigger array, copy the old clients, add the new one,
    // and only then release the old array.
    Client* bigger = new Client[num_clients + 1];
    for (int i = 0; i < num_clients; ++i) {
        bigger[i] = clients[i];
    }
    bigger[num_clients] = c;

    delete[] clients;
    clients = bigger;
    ++num_clients;
    return true;
}

// ---------------------------------------------------------------------------
// Saving
// ---------------------------------------------------------------------------

bool Bank::save_info(const std::string& filename) const {
    std::ofstream out(filename);
    if (!out) {
        return false;  // could not open the file for writing
    }

    out << std::fixed << std::setprecision(2);
    for (int i = 0; i < num_clients; ++i) {
        out << clients[i].client_name << ','
            << clients[i].ssn << ','
            << clients[i].bank_account_number << ','
            << clients[i].balance << '\n';
    }

    out.flush();
    return out.good();  // false if any write failed (e.g. disk full)
}

