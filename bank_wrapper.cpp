// C-compatible wrapper around the C++ Bank class, for use from Python (ctypes).
//
// Python cannot call C++ member functions or catch C++ exceptions, so every
// function here:
//   * has C linkage (extern "C") and uses only C types,
//   * takes the Bank as an opaque handle (void*),
//   * catches every C++ exception and returns a status code instead.
// No banking rules live here: the wrapper only translates calls and results.

#include "bank.h"

#include <cstddef>
#include <cstring>
#include <fstream>
#include <new>
#include <stdexcept>
#include <string>

#if defined(_WIN32)
#define BANK_API __declspec(dllexport)
#else
#define BANK_API __attribute__((visibility("default")))
#endif

extern "C" {

// Status codes returned to Python. bank_app.py declares the same numbers.
enum BankStatus {
    BANK_OK = 0,
    BANK_ERR_BAD_ARGUMENT = 1,        // null handle, null pointer or bad index
    BANK_ERR_INVALID_AMOUNT = 2,      // amount is not greater than zero
    BANK_ERR_ACCOUNT_NOT_FOUND = 3,
    BANK_ERR_INSUFFICIENT_FUNDS = 4,
    BANK_ERR_DUPLICATE_ACCOUNT = 5,
    BANK_ERR_INVALID_RECORD = 6,      // new client failed backend validation
    BANK_ERR_FILE = 7,                // file could not be opened or written
    BANK_ERR_MEMORY = 8,
    BANK_ERR_UNKNOWN = 99
};

// Fixed-size record used to hand one client back to Python.
// bank_app.py declares a ctypes.Structure with the same layout.
enum { BANK_TEXT_SIZE = 256 };

struct ClientInfo {
    char client_name[BANK_TEXT_SIZE];
    char ssn[BANK_TEXT_SIZE];
    char bank_account_number[BANK_TEXT_SIZE];
    double balance;
};

}  // extern "C"

namespace {

Bank* as_bank(void* handle) {
    return static_cast<Bank*>(handle);
}

// Copy a std::string into a fixed char buffer, always null-terminated.
void copy_text(const std::string& source, char* dest) {
    std::size_t length = source.size();
    if (length > BANK_TEXT_SIZE - 1) {
        length = BANK_TEXT_SIZE - 1;
    }
    std::memcpy(dest, source.c_str(), length);
    dest[length] = '\0';
}

void fill_info(const Client& client, ClientInfo* out) {
    copy_text(client.client_name, out->client_name);
    copy_text(client.ssn, out->ssn);
    copy_text(client.bank_account_number, out->bank_account_number);
    out->balance = client.balance;
}

}  // namespace

extern "C" {

// Create a Bank from a client file. Returns a handle, or NULL on failure.
// *status (if not NULL) receives BANK_OK or the reason for the failure.
BANK_API void* bank_create(const char* filename, int* status) {
    int code = BANK_OK;
    Bank* bank = nullptr;
    try {
        if (filename == nullptr || filename[0] == '\0') {
            code = BANK_ERR_BAD_ARGUMENT;
        } else {
            // The Bank constructor quietly starts empty when a file is missing.
            // The GUI needs to know, so check that the file opens first.
            std::ifstream probe(filename);
            if (!probe) {
                code = BANK_ERR_FILE;
            } else {
                probe.close();
                bank = new Bank(filename);
            }
        }
    } catch (const std::bad_alloc&) {
        code = BANK_ERR_MEMORY;
    } catch (...) {
        code = BANK_ERR_UNKNOWN;
    }
    if (status != nullptr) {
        *status = code;
    }
    return bank;
}

// Release a Bank created by bank_create. Safe to call with NULL.
BANK_API void bank_destroy(void* handle) {
    try {
        delete as_bank(handle);
    } catch (...) {
        // Never let an exception cross into Python.
    }
}

// Number of clients, or -1 if the handle is NULL.
BANK_API int bank_get_num_clients(void* handle) {
    if (handle == nullptr) {
        return -1;
    }
    try {
        return as_bank(handle)->get_num_clients();
    } catch (...) {
        return -1;
    }
}

// Copy the client at position index (0-based) into *out.
BANK_API int bank_get_client_at(void* handle, int index, ClientInfo* out) {
    if (handle == nullptr || out == nullptr) {
        return BANK_ERR_BAD_ARGUMENT;
    }
    try {
        const Bank* bank = as_bank(handle);
        if (index < 0 || index >= bank->get_num_clients()) {
            return BANK_ERR_BAD_ARGUMENT;
        }
        fill_info(bank->get_clients_info()[index], out);
        return BANK_OK;
    } catch (const std::bad_alloc&) {
        return BANK_ERR_MEMORY;
    } catch (...) {
        return BANK_ERR_UNKNOWN;
    }
}

// Look up a client by account number and copy it into *out.
BANK_API int bank_find_client(void* handle, const char* account, ClientInfo* out) {
    if (handle == nullptr || account == nullptr || out == nullptr) {
        return BANK_ERR_BAD_ARGUMENT;
    }
    try {
        const Client* client = as_bank(handle)->find_client(account);
        if (client == nullptr) {
            return BANK_ERR_ACCOUNT_NOT_FOUND;
        }
        fill_info(*client, out);
        return BANK_OK;
    } catch (const std::bad_alloc&) {
        return BANK_ERR_MEMORY;
    } catch (...) {
        return BANK_ERR_UNKNOWN;
    }
}

// Deposit into an account. On success *new_balance receives the new balance.
BANK_API int bank_deposit(void* handle, const char* account, double amount, double* new_balance) {
    if (handle == nullptr || account == nullptr || new_balance == nullptr) {
        return BANK_ERR_BAD_ARGUMENT;
    }
    try {
        *new_balance = as_bank(handle)->deposit(account, amount);
        return BANK_OK;
    } catch (const std::invalid_argument&) {
        return BANK_ERR_INVALID_AMOUNT;
    } catch (const std::out_of_range&) {
        return BANK_ERR_ACCOUNT_NOT_FOUND;
    } catch (const std::bad_alloc&) {
        return BANK_ERR_MEMORY;
    } catch (...) {
        return BANK_ERR_UNKNOWN;
    }
}

// Withdraw from an account. On success *new_balance receives the new balance.
BANK_API int bank_withdraw(void* handle, const char* account, double amount, double* new_balance) {
    if (handle == nullptr || account == nullptr || new_balance == nullptr) {
        return BANK_ERR_BAD_ARGUMENT;
    }
    try {
        *new_balance = as_bank(handle)->withdraw(account, amount);
        return BANK_OK;
    } catch (const std::invalid_argument&) {
        return BANK_ERR_INVALID_AMOUNT;
    } catch (const std::out_of_range&) {
        return BANK_ERR_ACCOUNT_NOT_FOUND;
    } catch (const std::bad_alloc&) {
        return BANK_ERR_MEMORY;
    } catch (const std::runtime_error&) {
        return BANK_ERR_INSUFFICIENT_FUNDS;
    } catch (...) {
        return BANK_ERR_UNKNOWN;
    }
}

// Add a client. The backend validates the record and rejects duplicates.
BANK_API int bank_add_client(void* handle, const char* name, const char* ssn,
                             const char* account, double balance) {
    if (handle == nullptr || name == nullptr || ssn == nullptr || account == nullptr) {
        return BANK_ERR_BAD_ARGUMENT;
    }
    try {
        Bank* bank = as_bank(handle);
        Client client;
        client.client_name = name;
        client.ssn = ssn;
        client.bank_account_number = account;
        client.balance = balance;

        if (bank->add_new_client(client)) {
            return BANK_OK;
        }
        // add_new_client gives one "rejected" answer for two reasons.
        // Ask the backend which one applies so the GUI can say why.
        if (bank->find_client(client.bank_account_number) != nullptr) {
            return BANK_ERR_DUPLICATE_ACCOUNT;
        }
        return BANK_ERR_INVALID_RECORD;
    } catch (const std::bad_alloc&) {
        return BANK_ERR_MEMORY;
    } catch (...) {
        return BANK_ERR_UNKNOWN;
    }
}

// Save every client to a CSV file.
BANK_API int bank_save(void* handle, const char* filename) {
    if (handle == nullptr || filename == nullptr || filename[0] == '\0') {
        return BANK_ERR_BAD_ARGUMENT;
    }
    try {
        return as_bank(handle)->save_info(filename) ? BANK_OK : BANK_ERR_FILE;
    } catch (const std::bad_alloc&) {
        return BANK_ERR_MEMORY;
    } catch (...) {
        return BANK_ERR_UNKNOWN;
    }
}

}  // extern "C"

