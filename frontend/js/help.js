// 사용 설명서 모달 - 도움말 버튼으로 언제든 열고 닫을 수 있고, 설치 후
// 최초 실행 때만 자동으로 한 번 뜬다(서버 DB에 "한 번이라도 띄운 적
// 있는지"를 저장해, 브라우저를 바꾸거나 캐시를 지워도 재실행 시 다시
// 뜨지 않는다).

import { api } from "./core.js";

export function openHelpModal() {
  document.getElementById("helpModalOverlay").hidden = false;
}

export function closeHelpModal() {
  document.getElementById("helpModalOverlay").hidden = true;
}

export function initHelpModal() {
  document.getElementById("helpBtn").addEventListener("click", openHelpModal);
  document.getElementById("helpModalCloseBtn").addEventListener("click", closeHelpModal);
  document.getElementById("helpModalOverlay").addEventListener("click", (ev) => {
    if (ev.target.id === "helpModalOverlay") closeHelpModal();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !document.getElementById("helpModalOverlay").hidden) closeHelpModal();
  });

  api("/api/settings/help-shown")
    .then((status) => {
      if (status.shown) return;
      openHelpModal();
      return api("/api/settings/help-shown", { method: "POST" });
    })
    .catch(() => { /* 서버가 아직 준비 안 됐어도 앱 초기화를 막지 않는다 */ });
}
