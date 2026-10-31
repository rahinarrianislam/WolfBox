import Foundation
import Security

struct KeychainStore {
    private let service = "org.wolfbox.demo.session"
    private func query(_ server: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service, kSecAttrAccount as String: server]
    }
    func read(server: String) -> String? {
        var q = query(server)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    func save(_ token: String, server: String) throws {
        let q = query(server)
        let values = [kSecValueData as String: Data(token.utf8)]
        let updated = SecItemUpdate(q as CFDictionary, values as CFDictionary)
        if updated == errSecSuccess { return }
        guard updated == errSecItemNotFound else { throw KeychainError(status: updated) }
        var entry = q.merging(values) { _, new in new }
        entry[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let status = SecItemAdd(entry as CFDictionary, nil)
        guard status == errSecSuccess else { throw KeychainError(status: status) }
    }
    func delete(server: String) { SecItemDelete(query(server) as CFDictionary) }
    struct KeychainError: LocalizedError {
        let status: OSStatus
        var errorDescription: String? { "Your session could not be saved in Keychain. Please try signing in again." }
    }
}
