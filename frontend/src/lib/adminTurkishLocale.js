const ADMIN_TEXT_REPLACEMENTS = [
  ["Live Gate", "Canlı Geçiş Kapısı"],
  ["Live Trading Dashboard", "Canlı İşlem Paneli"],
  ["System Status", "Sistem Durumu"],
  ["Scanner Monitor", "Tarayıcı İzleme"],
  ["Strategy Control", "Strateji Kontrol"],
  ["Strategy Allocation", "Strateji Dağılımı"],
  ["Strategy Intelligence", "Strateji Zekası"],
  ["Canonical Strategy Registry", "Kanonik Strateji Kayıtları"],
  ["Execution State Machine", "Yürütme Durum Makinesi"],
  ["Strategy Observability", "Strateji Gözlemlenebilirliği"],
  ["Risk Engine", "Risk Motoru"],
  ["Execution Monitor", "Yürütme İzleme"],
  ["Execution Readiness", "Yürütme Hazırlığı"],
  ["Operator Center", "Operatör Merkezi"],
  ["Incident Intelligence", "Olay Zekası"],
  ["Unified Control Room", "Birleşik Kontrol Odası"],
  ["Execution States", "Yürütme Durumları"],
  ["Execution Analytics", "Yürütme Analitiği"],
  ["Execution Failures", "Yürütme Hataları"],
  ["Idempotency Control", "İdempotensi Kontrolü"],
  ["Execution Trace", "Yürütme İz Kaydı"],
  ["Execution Alerts Delivery", "Yürütme Uyarı Teslimi"],
  ["Execution Rebuild", "Yürütme Yeniden Kurulumu"],
  ["Users", "Kullanıcılar"],
  ["USER USERS", "KULLANICILAR"],
  ["USER KULLANICILARI", "KULLANICILAR"],
  ["USER", "Kullanıcı"],
  ["ADMIN", "Yönetici"],
  ["Admin Users", "Admin Kullanıcıları"],
  ["User Users", "Kullanıcılar"],
  ["Commercial Ops", "Ticari Operasyonlar"],
  ["Revenue Engine", "Gelir Motoru"],
  ["User Economics", "Kullanıcı Ekonomisi"],
  ["Analytics Snapshots", "Analitik Anlık Görüntüler"],
  ["Credential Orchestration", "Kimlik Bilgisi Orkestrasyonu"],
  ["User Approvals", "Kullanıcı Onayları"],
  ["Onboarding Observability", "Onboarding Gözlemlenebilirliği"],
  ["Pipeline Operations", "Pipeline Operasyonları"],
  ["Exchange Settings", "Borsa Ayarları"],
  ["MFA Settings", "MFA Ayarları"],
  ["Brand Settings", "Marka Ayarları"],
  ["System Config", "Sistem Yapılandırması"],
  ["System Readiness", "Sistem Hazırlığı"],
  ["Anomaly Timeline", "Anomali Zaman Çizelgesi"],
  ["Dashboard", "Gösterge Paneli"],
  ["Trading Panel", "İşlem Paneli"],
  ["Trading Engine", "İşlem Motoru"],
  ["Industrial Cockpit", "Endüstriyel Kokpit"],
  ["active override", "aktif override"],
  ["expires in", "süre:"],
  ["expired", "süresi doldu"],
  ["Menu", "Menü"],
  ["Search", "Ara"],
  ["Approval Queue", "Onay Kuyruğu"],
  ["Approval Policies", "Onay Politikaları"],
  ["Custom Roles", "Özel Roller"],
  ["Invite Lifecycle", "Davet Yaşam Döngüsü"],
  ["Observability", "Gözlemlenebilirlik"],
  ["User Actions", "Kullanıcı İşlemleri"],
  ["Created", "Oluşturulma"],
  ["Refresh", "Yenile"],
  ["Pending", "Bekleyen"],
  ["Preview", "Önizleme"],
  ["Disable", "Devre Dışı"],
  ["Enable", "Etkinleştir"],
  ["Soft Delete", "Yumuşak Sil"],
  ["Bulk", "Toplu"],
  ["Next", "Sonraki"],
  ["Prev", "Önceki"],
  ["Scanner Active Mode Indicator", "Tarayıcı Aktif Mod Göstergesi"],
  ["Active Mode", "Aktif Mod"],
  ["Execution Path", "Yürütme Yolu"],
  ["Source", "Kaynak"],
  ["Run & Automation", "Çalıştırma ve Otomasyon"],
  ["Signal Mode", "Sinyal Modu"],
  ["Market Type", "Piyasa Tipi"],
  ["Auto Scan Interval", "Otomatik Tarama Aralığı"],
  ["No template", "Şablon yok"],
  ["Open template detail", "Şablon detayını aç"],
];

const ATTRIBUTE_KEYS = ["placeholder", "title", "aria-label"];
const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "CODE", "PRE", "TEXTAREA"]);

const shouldSkipText = (value) => {
  const trimmed = String(value || "").trim();
  if (!trimmed) return true;
  if (/^[A-Z0-9_:\-./]+$/.test(trimmed)) return true;
  if (/^\/?api\//i.test(trimmed)) return true;
  return false;
};

const translateText = (raw) => {
  let text = String(raw || "");
  for (const [source, target] of ADMIN_TEXT_REPLACEMENTS) {
    if (!source || !target) continue;
    text = text.replaceAll(source, target);
  }
  return text;
};

export const localizeAdminDomToTurkish = (root = document.body) => {
  if (!root) return;

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    const parent = node.parentElement;
    if (parent && !SKIP_TAGS.has(parent.tagName) && !parent.closest("[data-no-auto-translate='true']")) {
      const rawText = node.nodeValue || "";
      if (!shouldSkipText(rawText)) {
        const translated = translateText(rawText);
        if (translated !== rawText) {
          node.nodeValue = translated;
        }
      }
    }
    node = walker.nextNode();
  }

  const elements = root.querySelectorAll("*");
  elements.forEach((element) => {
    if (SKIP_TAGS.has(element.tagName) || element.closest("[data-no-auto-translate='true']")) {
      return;
    }
    ATTRIBUTE_KEYS.forEach((key) => {
      const raw = element.getAttribute(key);
      if (!raw || shouldSkipText(raw)) return;
      const translated = translateText(raw);
      if (translated !== raw) {
        element.setAttribute(key, translated);
      }
    });
  });
};
