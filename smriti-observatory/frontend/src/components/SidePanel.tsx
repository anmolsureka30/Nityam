import { useRef, useState } from "react";
import styles from "./SidePanel.module.css";

export interface SidePanelTab {
  id: string;
  label: string;
  content: React.ReactNode;
}

interface SidePanelProps {
  tabs: SidePanelTab[];
  defaultWidth?: number;
  minWidth?: number;
  maxWidthVw?: number;
}

export function SidePanel({ tabs, defaultWidth = 480, minWidth = 360, maxWidthVw = 50 }: SidePanelProps) {
  const [width, setWidth] = useState(defaultWidth);
  const [activeTab, setActiveTab] = useState(tabs[0]?.id);
  const dragging = useRef(false);

  const onPointerDown = () => {
    dragging.current = true;
    const onMove = (event: PointerEvent) => {
      if (!dragging.current) return;
      const maxWidth = (window.innerWidth * maxWidthVw) / 100;
      setWidth(Math.min(maxWidth, Math.max(minWidth, window.innerWidth - event.clientX)));
    };
    const onUp = () => {
      dragging.current = false;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <aside className={styles.panel} style={{ width }}>
      <div className={styles.resizeHandler} onPointerDown={onPointerDown} data-testid="resize-handler" />
      <div className={styles.tabBar} role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className={styles.tabContent}>{tabs.find((t) => t.id === activeTab)?.content}</div>
    </aside>
  );
}
