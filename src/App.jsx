import React from "react";

const essentialApps = [
  { name: "Phone", icon: "📞" },
  { name: "Messages", icon: "✉️" },
  { name: "Contacts", icon: "👥" },
  { name: "Settings", icon: "⚙️" },
  { name: "Camera", icon: "📷" },
  { name: "Gallery", icon: "🌄" },
  { name: "Clock", icon: "⏰" },
  { name: "Calculator", icon: "📈" },
  { name: "Chrome", icon: "🌐" },
  { name: "YouTube", icon: "📺" },
];

const App = () => {
  const openApp = (appName) => {
    alert(`This would open: ${appName}`);
  };

  const identifySong = () => {
    alert("Opening Shazam to identify song...");
  };

  const uninstallLauncher = () => {
    alert("This would take you to the launcher uninstall settings.");
  };

  return (
    <div style={styles.container}>
      <div style={styles.widgetCard}>
        <div style={styles.clockIcon}>⏰</div>
        <div style={styles.timeText}>12:34</div>
        <div style={styles.eventText}>Today's Events: None</div>
      </div>

      <div style={styles.appGrid}>
        {essentialApps.map((app) => (
          <div key={app.name} style={styles.appCard} onClick={() => openApp(app.name)}>
            <div style={styles.icon}>{app.icon}</div>
            <div style={styles.appText}>{app.name}</div>
          </div>
        ))}
      </div>

      <button style={styles.shazamButton} onClick={identifySong}>
        Identify Song
      </button>

      <button style={styles.uninstallButton} onClick={uninstallLauncher}>
        Uninstall Launcher
      </button>
    </div>
  );
};

const styles = {
  container: {
    backgroundColor: "black",
    color: "white",
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: 20,
    fontFamily: "sans-serif",
  },
  widgetCard: {
    backgroundColor: "#222",
    width: "90%",
    padding: 20,
    borderRadius: 15,
    textAlign: "center",
    marginBottom: 20,
  },
  clockIcon: {
    fontSize: 36,
    marginBottom: 10,
  },
  timeText: {
    fontSize: 32,
    fontWeight: "bold",
  },
  eventText: {
    fontSize: 14,
    color: "gray",
  },
  appGrid: {
    display: "flex",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: 15,
    maxWidth: 350,
    marginBottom: 20,
  },
  appCard: {
    width: 60,
    height: 60,
    backgroundColor: "#333",
    borderRadius: 15,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
  },
  icon: {
    fontSize: 24,
  },
  appText: {
    fontSize: 10,
    marginTop: 5,
  },
  shazamButton: {
    backgroundColor: "#0088FF",
    color: "white",
    padding: "12px 24px",
    borderRadius: 10,
    border: "none",
    marginBottom: 10,
    cursor: "pointer",
    fontSize: 16,
  },
  uninstallButton: {
    backgroundColor: "#FF4444",
    color: "white",
    padding: "12px 24px",
    borderRadius: 10,
    border: "none",
    cursor: "pointer",
    fontSize: 16,
  },
};

export default App;