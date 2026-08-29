import { useEffect, useState } from "react";
import { View, Text, FlatList, TouchableOpacity, StyleSheet, Alert } from "react-native";
import { getProjectTasks, triggerDeploy } from "../api";

const STATUS_COLORS = {
  pending: "#5c4a70", in_progress: "#ffd166", blocked: "#ff5fa2",
  in_review: "#4dd8ff", done: "#7CFFB2", failed: "#ff5f5f",
};

export default function ProjectDetailScreen({ project, onBack }) {
  const [tasks, setTasks] = useState([]);
  const [deploying, setDeploying] = useState(false);

  useEffect(() => {
    getProjectTasks(project.id).then(setTasks).catch(() => {});
  }, [project.id]);

  const handleDeploy = async () => {
    setDeploying(true);
    try {
      await triggerDeploy(project.id);
      Alert.alert("Deploy started", "Watch progress on the web app's live feed.");
    } catch (e) {
      Alert.alert("Deploy failed to start", e.message);
    } finally {
      setDeploying(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.headerRow}>
        <TouchableOpacity onPress={onBack}><Text style={styles.back}>{"< Back"}</Text></TouchableOpacity>
        <Text style={styles.header}>{project.name}</Text>
        <View style={{ width: 40 }} />
      </View>
      <TouchableOpacity style={styles.deployButton} onPress={handleDeploy} disabled={deploying}>
        <Text style={styles.deployText}>{deploying ? "Starting..." : "Deploy Now"}</Text>
      </TouchableOpacity>
      <FlatList
        data={tasks}
        keyExtractor={(t) => t.id}
        contentContainerStyle={{ padding: 16 }}
        renderItem={({ item }) => (
          <View style={styles.taskCard}>
            <View style={styles.taskHeader}>
              <Text style={styles.taskTitle}>{item.title}</Text>
              <View style={[styles.badge, { backgroundColor: STATUS_COLORS[item.status] || "#5c4a70" }]}>
                <Text style={styles.badgeText}>{item.status}</Text>
              </View>
            </View>
            <Text style={styles.taskRole}>{item.assigned_role.replace("_", " ")}</Text>
          </View>
        )}
        ListEmptyComponent={<Text style={styles.empty}>No tasks yet.</Text>}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#1a0f26" },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 16, paddingBottom: 0 },
  back: { color: "#ffd166", fontWeight: "700" },
  header: { color: "#fff", fontWeight: "800", fontSize: 16 },
  deployButton: {
    margin: 16, backgroundColor: "#ff5fa2", borderRadius: 12, padding: 14, alignItems: "center",
  },
  deployText: { color: "#241533", fontWeight: "800" },
  taskCard: {
    backgroundColor: "#ffffff10", borderRadius: 12, padding: 14, marginBottom: 10,
    borderWidth: 1, borderColor: "#ffffff1a",
  },
  taskHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  taskTitle: { color: "#fff", fontWeight: "700", flex: 1, marginRight: 8 },
  taskRole: { color: "#b8a7cc", marginTop: 4, fontSize: 12, textTransform: "capitalize" },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  badgeText: { color: "#241533", fontSize: 10, fontWeight: "800" },
  empty: { color: "#b8a7cc", textAlign: "center", marginTop: 40 },
});
