import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the built dist/ can be served from any subdirectory, not just a
// domain root. Note the build still needs to be *served* — its entry is an ES module,
// which browsers refuse to load over file://. Use `npm run preview`, or open
// standalone.html for the no-server version.
export default defineConfig({
  plugins: [react()],
  base: "./",
});
