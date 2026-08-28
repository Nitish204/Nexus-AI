import { StatusBar } from "expo-status-bar";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import ProjectsScreen from "./screens/ProjectsScreen";
import ProjectDetailScreen from "./screens/ProjectDetailScreen";
import LoginScreen from "./screens/LoginScreen";

const Stack = createNativeStackNavigator();

// NEXUS Mobile Companion — a lightweight read/act client for the same
// backend the web app uses. Purpose: check on a running build, glance
// at the live agent feed, and trigger a deploy, from your phone —
// not a full workspace replacement (no 3D scene, no in-browser editor).
export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Stack.Navigator
        initialRouteName="Login"
        screenOptions={{
          headerStyle: { backgroundColor: "#241533" },
          headerTintColor: "#fff",
          headerTitleStyle: { fontWeight: "800" },
        }}
      >
        <Stack.Screen name="Login" component={LoginScreen} options={{ title: "NEXUS" }} />
        <Stack.Screen name="Projects" component={ProjectsScreen} options={{ title: "Your Projects" }} />
        <Stack.Screen name="ProjectDetail" component={ProjectDetailScreen} options={{ title: "Project" }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
