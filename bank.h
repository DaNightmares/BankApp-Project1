
#ifndef BANK_H
#define BANK_H

#include <string>

// One client record. Field order matches the CSV file:
// client_name,ssn,bank_account_number,balance
struct Client {
    std::string client_name;          // Client's full name
    std::string ssn;                  // Fictitious SSN / identifier
    std::string bank_account_number;  // Unique bank account identifier
    double balance;                   // Current account balance
};

class Bank {
public:
    // Construction and file loading
    explicit Bank(const std::string& filename);

    // Rule of Three
    ~Bank();
    Bank(const Bank& other);
    Bank& operator=(const Bank& other);

    // Client access / search (nothing here prints)
    const Client* get_clients_info() const;  // pointer to the first client, or nullptr if empty
    int get_num_clients() const;
    const Client* find_client(const std::string& bank_account_number) const;  // nullptr if not found

    // Transactions: return the new balance, throw on a rejected request
    //   std::invalid_argument - amount is not positive
    //   std::out_of_range     - account number not found
    //   std::runtime_error    - insufficient funds (withdraw only)
    double deposit(const std::string& bank_account_number, double amount);
    double withdraw(const std::string& bank_account_number, double amount);

    // Returns false if the record is invalid or the account number already exists
    bool add_new_client(const Client& new_client);

    // Returns false if the file could not be opened or written
    bool save_info(const std::string& filename) const;

private:
    int num_clients;   // Number of valid Client objects stored in the dynamic array
    Client* clients;   // Pointer to a dynamically allocated array of Client objects

    // Private helpers (functions only, no extra data members)
    int find_index(const std::string& bank_account_number) const;  // -1 if not found
    static bool is_valid(const Client& c);
    static bool parse_line(const std::string& line, Client& out);
};

#endif  // BANK_H
