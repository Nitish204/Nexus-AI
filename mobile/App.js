import { useState } from "react";
import { StatusBar } from "expo-status-bar";
import { SafeAreaView, StyleSheet } from "react-native";
import ProjectsScreen from "./screens/ProjectsScreen";
import ProjectDetailScreen from "./screens/ProjectDetailScreen";
import LoginScreen from "./screens/LoginScreen";

// NEXUS Mobile Companion — screen switching done with plain React state
// instead of @react-navigation, since that package won't bundle inside
// Snack's web-based bundler right now. Same end result, no extra
// navigation dependency needed.
export default function App() {
  const [screen, setScreen] = useState("login"); // "login" | "projects" | "detail"
  const [selectedProject, setSelectedProject] = useState(null);

  const goToProjects = () => setScreen("projects");
  const openProject = (project) => {
    setSelectedProject(project);
    setScreen("detail");
  };
  const goBack = () => setScreen("projects");

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      {screen === "login" && <LoginScreen onLoggedIn={goToProjects} />}
      {screen === "projects" && <ProjectsScreen onSelectProject={openProject} />}
      {screen === "detail" && selectedProject && (
        <ProjectDetailScreen project={selectedProject} onBack={goBack} />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#1a0f26" },
});
