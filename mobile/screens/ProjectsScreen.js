import { useEffect, useState, useCallback } from "react";
import { View, Text, FlatList, TouchableOpacity, StyleSheet, RefreshControl } from "react-native";
import { listProjects } from "../api";

export default function ProjectsScreen({ onSelectProject }) {
  const [projects, setProjects] = useState([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setProjects(await listProjects());
    } catch (e) {
      // Swallow — an empty list with pull-to-refresh still available is
      // a reasonable fallback state for a companion app.
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <View style={styles.container}>
      <Text style={styles.header}>Your Projects</Text>
      <FlatList
        data={projects}
        keyExtractor={(item) => item.id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} tintColor="#fff" />}
        contentContainerStyle={{ padding: 16 }}
        ListEmptyComponent={<Text style={styles.empty}>No projects yet — create one on the web app.</Text>}
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.card} onPress={() => onSelectProject(item)}>
            <Text style={styles.cardTitle}>{item.name}</Text>
            <Text style={styles.cardDesc} numberOfLines={2}>{item.description || "No description"}</Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#1a0f26" },
  header: { color: "#fff", fontWeight: "800", fontSize: 20, padding: 16, paddingBottom: 0 },
  card: {
    backgroundColor: "#ffffff10", borderRadius: 14, padding: 16, marginBottom: 12,
    borderWidth: 1, borderColor: "#ffffff1a",
  },
  cardTitle: { color: "#fff", fontWeight: "800", fontSize: 16 },
  cardDesc: { color: "#b8a7cc", marginTop: 4 },
  empty: { color: "#b8a7cc", textAlign: "center", marginTop: 60 },
});
