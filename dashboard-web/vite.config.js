import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages 주소가 https://<계정>.github.io/pitch-signal/ 이므로 base를 맞춘다 (SPEC 3.17).
export default defineConfig({
  define: { __BUILD__: JSON.stringify(new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")) },   // 데이터 요청의 캐시 깨기용 빌드 번호
  plugins: [react()],
  base: "/pitch-signal/",
});
