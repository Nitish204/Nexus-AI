import { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator } from "react-native";
import { login } from "../api";

export default function LoginScreen({ onLoggedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      onLoggedIn();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>NEXUS</Text>
      <Text style={styles.subtitle}>Companion — check your builds on the go</Text>
      <TextInput
        style={styles.input}
        placeholder="Email"
        placeholderTextColor="#5c4a70"
        autoCapitalize="none"
        value={email}
        onChangeText={setEmail}
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        placeholderTextColor="#5c4a70"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <TouchableOpacity style={styles.button} onPress={handleLogin} disabled={loading}>
        {loading ? <ActivityIndicator color="#241533" /> : <Text style={styles.buttonText}>Sign In</Text>}
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#241533", justifyContent: "center", padding: 24 },
  title: { fontSize: 40, fontWeight: "900", color: "#fff", textAlign: "center" },
  subtitle: { color: "#b8a7cc", textAlign: "center", marginBottom: 32 },
  input: {
    backgroundColor: "#ffffff12", color: "#fff", borderRadius: 12, padding: 14,
    marginBottom: 14, borderWidth: 1, borderColor: "#ffffff22",
  },
  button: { backgroundColor: "#ffd166", borderRadius: 12, padding: 14, alignItems: "center", marginTop: 8 },
  buttonText: { color: "#241533", fontWeight: "800" },
  error: { color: "#ff5fa2", marginBottom: 10, fontWeight: "600" },
});
