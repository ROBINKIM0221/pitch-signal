import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages 주소가 https://<계정>.github.io/pitch-signal/ 이므로 base를 맞춘다 (SPEC 3.17).
export default defineConfig({
  plugins: [react()],
  base: "/pitch-signal/",
});
