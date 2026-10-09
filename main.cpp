// Console driver that exercises the Bank backend.
// All printing lives here; the Bank class itself never prints.

#include "bank.h"

#include <exception>
#include <iomanip>
#include <iostream>
#include <string>

void print_clients(const Bank& bank) {
    const Client* list = bank.get_clients_info();
    for (int i = 0; i < bank.get_num_clients(); ++i) {
        std::cout << "  " << std::left << std::setw(18) << list[i].client_name
                  << std::setw(14) << list[i].ssn
                  << std::setw(10) << list[i].bank_account_number
                  << std::right << std::setw(10) << list[i].balance << '\n';
    }
}

void try_deposit(Bank& bank, const std::string& account, double amount) {
    try {
        const double balance = bank.deposit(account, amount);
        std::cout << "  Deposit " << amount << " to " << account
                  << " -> new balance " << balance << '\n';
    } catch (const std::exception& e) {
        std::cout << "  Deposit " << amount << " to " << account
                  << " rejected: " << e.what() << '\n';
    }
}

void try_withdraw(Bank& bank, const std::string& account, double amount) {
    try {
        const double balance = bank.withdraw(account, amount);
        std::cout << "  Withdraw " << amount << " from " << account
                  << " -> new balance " << balance << '\n';
    } catch (const std::exception& e) {
        std::cout << "  Withdraw " << amount << " from " << account
                  << " rejected: " << e.what() << '\n';
    }
}

void try_add(Bank& bank, const std::string& name, const std::string& ssn,
             const std::string& account, double balance) {
    Client c;
    c.client_name = name;
    c.ssn = ssn;
    c.bank_account_number = account;
    c.balance = balance;
    std::cout << "  Add \"" << name << "\" (" << account << "): "
              << (bank.add_new_client(c) ? "added" : "rejected") << '\n';
}

int main(int argc, char* argv[]) {
    const std::string filename = (argc > 1) ? argv[1] : "clients.csv";
    std::cout << std::fixed << std::setprecision(2);

    // 1. Construction and file loading
    Bank bank(filename);
    std::cout << "Loaded " << bank.get_num_clients() << " client(s) from " << filename << '\n';
    print_clients(bank);

    // 2. Search
    std::cout << "\nSearch\n";
    const Client* found = bank.find_client("ACC1002");
    if (found != nullptr) {
        std::cout << "  ACC1002 belongs to " << found->client_name << '\n';
    } else {
        std::cout << "  ACC1002 not found\n";
    }
    std::cout << "  ACC9999 " << (bank.find_client("ACC9999") ? "found" : "not found") << '\n';

    // 3. Deposits
    std::cout << "\nDeposits\n";
    try_deposit(bank, "ACC1001", 250.00);
    try_deposit(bank, "ACC1001", -5.00);   // non-positive amount
    try_deposit(bank, "ACC9999", 100.00);  // unknown account

    // 4. Withdrawals
    std::cout << "\nWithdrawals\n";
    try_withdraw(bank, "ACC1002", 100.00);
    try_withdraw(bank, "ACC1002", 0.00);        // non-positive amount
    try_withdraw(bank, "ACC9999", 10.00);       // unknown account
    try_withdraw(bank, "ACC1003", 1000000.00);  // insufficient funds

    // 5. Adding clients
    std::cout << "\nNew clients\n";
    try_add(bank, "Dana Whitfield", "000-00-0004", "ACC1004", 500.00);
    try_add(bank, "Copy Cat", "000-00-0005", "ACC1001", 10.00);  // duplicate account number
    try_add(bank, "", "000-00-0006", "ACC1006", 10.00);          // empty name
    try_add(bank, "Neg Balance", "000-00-0007", "ACC1007", -1.00);  // negative balance

    // 6. Rule of Three: copies must be independent of the original
    std::cout << "\nDeep copy check\n";
    Bank copy(bank);             // copy constructor
    copy.deposit("ACC1001", 1000.00);
    Bank assigned("no_such_file.csv");
    assigned = bank;             // copy assignment
    assigned.withdraw("ACC1001", 1.00);
    std::cout << "  original ACC1001: " << bank.find_client("ACC1001")->balance << '\n';
    std::cout << "  copy     ACC1001: " << copy.find_client("ACC1001")->balance << '\n';
    std::cout << "  assigned ACC1001: " << assigned.find_client("ACC1001")->balance << '\n';

    // 7. Saving, then reloading to confirm the file round-trips
    std::cout << "\nSaving\n";
    const std::string out_file = "clients_saved.csv";
    if (bank.save_info(out_file)) {
        std::cout << "  Saved " << bank.get_num_clients() << " client(s) to " << out_file << '\n';
    } else {
        std::cout << "  Could not save to " << out_file << '\n';
    }
    std::cout << "  Save to a bad path: "
              << (bank.save_info("no_such_folder/clients.csv") ? "saved" : "reported an error") << '\n';

    Bank reloaded(out_file);
    std::cout << "\nReloaded " << reloaded.get_num_clients() << " client(s) from " << out_file << '\n';
    print_clients(reloaded);

    return 0;
}

