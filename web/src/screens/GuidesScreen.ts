// Learn to Play — port of screens/guides.py + screens/unit_overview.py.
// Data comes from src/generated/gamedata.json, which tools/gen_docs.py
// regenerates from the Python config (also run automatically by the npm
// predev/prebuild sync-assets step), so every number shown here tracks
// config/settings.py + config/unit_types.py.

import { Screen, type Transition } from "../app/Screen";
import type { App } from "../app/App";
import {
  MENU_BG,
  SIDEBAR_BG,
  SIDEBAR_WIDTH,
  SIDEBAR_BTN_HEIGHT,
  CONTENT_TEXT,
  CONTENT_HEADING,
  CONTENT_FONT_SIZE,
  HEADING_FONT_SIZE,
  TG_ACTIVE,
  TG_INACTIVE,
  TG_BORDER,
  rgb,
  type RGB,
} from "../ui/theme";
import { drawText, measure } from "../ui/Text";
import gamedataJson from "../generated/gamedata.json";

// -- gamedata typing ----------------------------------------------------------

interface WeaponData {
  damage: number;
  range: number;
  cooldown: number;
  splash_radius?: number;
  splash_damage_max?: number;
  splash_damage_min?: number;
  hits_only_friendly?: boolean;
}

interface UnitData {
  hp: number;
  speed: number;
  radius: number;
  symbol: number[][] | null;
  can_attack: boolean;
  fov?: number;
  spawn_count?: number;
  is_t2?: boolean;
  weapon?: WeaponData;
}

interface PassiveCard {
  name: string;
  desc: string;
}

interface GameData {
  unit_types: Record<string, UnitData>;
  t2_names: Record<string, string>;
  spawnable_types: string[];
  building_types: string[];
  unit_passives: Record<string, PassiveCard[]>;
  guide_topics: { title: string; lines: string[] }[];
  command_center: {
    hp: number;
    radius: number;
    laser_range: number;
    laser_damage: number;
    laser_cooldown: number;
  };
}

const DATA = gamedataJson as unknown as GameData;

const TEAM1_COLOR: RGB = [80, 140, 255];
const TEAM1_OUTLINE: RGB = [150, 220, 255];
const DIFF_BETTER: RGB = [100, 255, 100];
const DIFF_WORSE: RGB = [255, 100, 100];

function titleCase(ut: string): string {
  return ut
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function t2Name(baseType: string): string {
  return DATA.t2_names[baseType] ?? `${titleCase(baseType)} T2`;
}

function fmt(x: number): string {
  return Number.isInteger(x) ? String(x) : String(Math.round(x * 100) / 100);
}

interface StatRow {
  label: string;
  value: string;
  diff: string; // e.g. " (+10)"
  lowerIsBetter: boolean;
}

export class GuidesScreen extends Screen {
  private mode: "topics" | "units" = "topics";
  private topicIdx = 0;
  private unitIdx = 0;
  private showT2 = false;
  private unitList: string[];

  constructor(app: App) {
    super(app);
    this.unitList = [...DATA.spawnable_types, ...DATA.building_types];
  }

  render(): Transition | null {
    const { ui } = this;
    const ctx = ui.ctx;
    ui.fillRect(0, 0, ui.w, ui.h, MENU_BG);
    ui.fillRect(0, 0, SIDEBAR_WIDTH, ui.h, SIDEBAR_BG);

    // Back: units mode returns to topics; topics returns to the main menu.
    if (ui.button("guides.back", 12, 12, SIDEBAR_WIDTH - 24, 32, "< Back", { fontSize: 16 })) {
      if (this.mode === "units") {
        this.mode = "topics";
        return null;
      }
      return { next: "main_menu" };
    }

    return this.mode === "topics" ? this.renderTopics(ctx) : this.renderUnits(ctx);
  }

  // -- sidebar rows -------------------------------------------------------

  private sidebarRow(id: string, index: number, label: string, active: boolean): boolean {
    const { ui } = this;
    const y = 60 + index * SIDEBAR_BTN_HEIGHT;
    const hover = !active && this.pointIn(0, y, SIDEBAR_WIDTH, SIDEBAR_BTN_HEIGHT);
    const bg = active ? TG_ACTIVE : hover ? TG_BORDER : TG_INACTIVE;
    ui.fillRect(0, y, SIDEBAR_WIDTH, SIDEBAR_BTN_HEIGHT, bg);
    ui.ctx.strokeStyle = rgb(TG_BORDER);
    ui.ctx.lineWidth = 1;
    ui.ctx.beginPath();
    ui.ctx.moveTo(0, y + SIDEBAR_BTN_HEIGHT + 0.5);
    ui.ctx.lineTo(SIDEBAR_WIDTH, y + SIDEBAR_BTN_HEIGHT + 0.5);
    ui.ctx.stroke();
    drawText(ui.ctx, label, 12, y + SIDEBAR_BTN_HEIGHT / 2, {
      size: CONTENT_FONT_SIZE,
      color: active ? [255, 255, 255] : CONTENT_TEXT,
      baseline: "middle",
    });
    void id;
    return hover && this.ui.input.released;
  }

  private pointIn(x: number, y: number, w: number, h: number): boolean {
    const { mouseX, mouseY } = this.ui.input;
    return mouseX >= x && mouseX <= x + w && mouseY >= y && mouseY <= y + h;
  }

  // -- topics mode ---------------------------------------------------------

  private renderTopics(ctx: CanvasRenderingContext2D): Transition | null {
    const topics = DATA.guide_topics;
    for (let i = 0; i < topics.length; i++) {
      const isLink = i === topics.length - 1;
      const label = topics[i].title + (isLink ? " >" : "");
      if (this.sidebarRow(`guides.topic.${i}`, i, label, i === this.topicIdx)) {
        if (isLink) {
          this.mode = "units";
          this.showT2 = false;
          return null;
        }
        this.topicIdx = i;
      }
    }

    const contentX = SIDEBAR_WIDTH + 20;
    const contentW = this.ui.w - SIDEBAR_WIDTH - 40;
    const topic = topics[this.topicIdx];
    drawText(ctx, topic.title, contentX, 20, {
      size: HEADING_FONT_SIZE,
      color: CONTENT_HEADING,
      bold: true,
    });

    let y = 60;
    for (const line of topic.lines) {
      if (!line) {
        y += 10;
        continue;
      }
      for (const wline of wrapText(ctx, line, contentW)) {
        drawText(ctx, wline, contentX, y, { size: CONTENT_FONT_SIZE, color: CONTENT_TEXT });
        y += CONTENT_FONT_SIZE + 6;
      }
    }
    return null;
  }

  // -- units mode ----------------------------------------------------------

  private renderUnits(ctx: CanvasRenderingContext2D): Transition | null {
    for (let i = 0; i < this.unitList.length; i++) {
      if (this.sidebarRow(`guides.unit.${i}`, i, titleCase(this.unitList[i]), i === this.unitIdx)) {
        this.unitIdx = i;
        this.showT2 = false;
      }
    }

    const baseType = this.unitList[this.unitIdx];
    const t2Key = `${baseType}_t2`;
    const hasT2 = t2Key in DATA.unit_types;
    const utype = this.showT2 && hasT2 ? t2Key : baseType;
    const stats = DATA.unit_types[utype];

    const contentX = SIDEBAR_WIDTH + 30;
    const contentW = this.ui.w - SIDEBAR_WIDTH - 60;

    const heading = this.showT2 && hasT2 ? t2Name(baseType) : titleCase(baseType);
    drawText(ctx, heading, contentX, 20, {
      size: HEADING_FONT_SIZE,
      color: CONTENT_HEADING,
      bold: true,
    });

    if (hasT2) {
      const bx = contentX + measure(ctx, heading, HEADING_FONT_SIZE, true) + 15;
      if (this.ui.button("guides.t2toggle", bx, 18, 100, 28, this.showT2 ? "Show T1" : "Show T2", { fontSize: 15 })) {
        this.showT2 = !this.showT2;
      }
    }

    // Symbol + FOV preview
    const symCx = contentX + contentW / 2;
    const symCy = 115;
    this.drawFovPreview(ctx, stats, symCx, symCy);
    this.drawUnitSymbol(ctx, utype, stats, symCx, symCy, 4.0);

    // Stats table (with diffs vs T1 when showing T2)
    const t1Stats = this.showT2 && hasT2 ? DATA.unit_types[baseType] : null;
    const bottom = this.drawStats(ctx, stats, utype, contentX, contentW, 200, t1Stats);

    // Passive cards
    const passives = DATA.unit_passives[utype] ?? [];
    this.drawPassives(ctx, passives, contentX, contentW, bottom + 14);
    return null;
  }

  private drawUnitSymbol(
    ctx: CanvasRenderingContext2D,
    utype: string,
    stats: UnitData,
    cx: number,
    cy: number,
    scale: number,
  ): void {
    const poly = (pts: [number, number][]) => {
      ctx.beginPath();
      pts.forEach(([px, py], i) => (i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)));
      ctx.closePath();
      ctx.fillStyle = rgb(TEAM1_COLOR);
      ctx.fill();
      ctx.strokeStyle = rgb(TEAM1_OUTLINE);
      ctx.lineWidth = 2;
      ctx.stroke();
    };

    if (utype === "command_center") {
      const r = DATA.command_center.radius * scale;
      const pts: [number, number][] = [];
      for (let i = 0; i < 6; i++) {
        const a = (Math.PI / 3) * i + Math.PI / 6;
        pts.push([cx + r * Math.cos(a), cy + r * Math.sin(a)]);
      }
      poly(pts);
    } else if (utype === "metal_extractor") {
      const r = stats.radius * scale;
      const s = (r * Math.sqrt(3)) / 2;
      poly([
        [cx, cy - r],
        [cx - s, cy + r / 2],
        [cx + s, cy + r / 2],
      ]);
    } else if (stats.symbol) {
      poly(stats.symbol.map(([px, py]) => [cx + px * scale, cy + py * scale]));
    } else {
      ctx.beginPath();
      ctx.arc(cx, cy, stats.radius * scale, 0, Math.PI * 2);
      ctx.fillStyle = rgb(TEAM1_COLOR);
      ctx.fill();
      ctx.strokeStyle = rgb(TEAM1_OUTLINE);
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }

  private drawFovPreview(ctx: CanvasRenderingContext2D, stats: UnitData, cx: number, cy: number): void {
    const fovDeg = stats.fov ?? 90;
    const fovRad = (fovDeg * Math.PI) / 180;
    const r = 55;
    if (fovRad >= Math.PI * 2 - 0.01) {
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255,0,255,0.16)";
      ctx.fill();
      ctx.strokeStyle = "rgba(255,0,255,0.28)";
      ctx.lineWidth = 1;
      ctx.stroke();
      return;
    }
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, -fovRad / 2, fovRad / 2); // facing right, like pygame
    ctx.closePath();
    ctx.fillStyle = "rgba(255,0,255,0.10)";
    ctx.fill();
    ctx.strokeStyle = "rgba(255,0,255,0.28)";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  private drawStats(
    ctx: CanvasRenderingContext2D,
    stats: UnitData,
    utype: string,
    contentX: number,
    contentW: number,
    yStart: number,
    t1Stats: UnitData | null,
  ): number {
    const rows: StatRow[] = [];
    const add = (
      label: string,
      val: number | string,
      t1Val?: number | null,
      opts: { suffix?: string; lowerIsBetter?: boolean } = {},
    ) => {
      const suffix = opts.suffix ?? "";
      let diff = "";
      if (t1Stats && typeof val === "number" && t1Val !== undefined && t1Val !== null && val !== t1Val) {
        const d = Math.round((val - t1Val) * 100) / 100;
        diff = ` (${d > 0 ? "+" : ""}${fmt(d)}${suffix})`;
      }
      rows.push({
        label,
        value: typeof val === "number" ? fmt(val) + suffix : val,
        diff,
        lowerIsBetter: opts.lowerIsBetter ?? false,
      });
    };

    add("HP", stats.hp, t1Stats?.hp);
    add("Speed", stats.speed, t1Stats?.speed);
    add("Radius", stats.radius, t1Stats?.radius);
    add("FOV", `${fmt(stats.fov ?? 90)}°`);

    let wpn: WeaponData | undefined = stats.weapon;
    if (utype === "command_center") {
      const cc = DATA.command_center;
      wpn = { damage: cc.laser_damage, range: cc.laser_range, cooldown: cc.laser_cooldown };
    }
    const t1Wpn = t1Stats?.weapon;

    if (wpn && (stats.can_attack || utype === "command_center") && !(wpn.damage === 0)) {
      if (wpn.damage < 0) {
        add("Heal/pulse", Math.abs(wpn.damage), t1Wpn ? Math.abs(t1Wpn.damage) : null);
      } else {
        add("Damage", wpn.damage, t1Wpn?.damage);
      }
      add("Range", wpn.range, t1Wpn?.range);
      add("Cooldown", wpn.cooldown, t1Wpn?.cooldown, { suffix: "s", lowerIsBetter: true });
      if (wpn.cooldown > 0) {
        const dps = Math.abs(wpn.damage) / wpn.cooldown;
        const t1Dps = t1Wpn && t1Wpn.cooldown > 0 ? Math.abs(t1Wpn.damage) / t1Wpn.cooldown : null;
        const label = wpn.damage < 0 ? "HPS" : "DPS";
        const diff =
          t1Dps !== null && Math.abs(dps - t1Dps) > 0.05
            ? ` (${dps - t1Dps > 0 ? "+" : ""}${(Math.round((dps - t1Dps) * 10) / 10).toFixed(1)})`
            : "";
        rows.push({ label, value: dps.toFixed(1), diff, lowerIsBetter: false });
      }
      if ((wpn.splash_radius ?? 0) > 0) {
        add("Splash Radius", wpn.splash_radius!, t1Wpn?.splash_radius);
        add("Splash Dmg", `${fmt(wpn.splash_damage_max ?? 0)}-${fmt(wpn.splash_damage_min ?? 0)}`);
      }
    } else if (!stats.can_attack) {
      rows.push({ label: "Can Attack", value: "No", diff: "", lowerIsBetter: false });
    }

    const spawnCount = stats.spawn_count ?? 1;
    if (spawnCount > 1) {
      add("Spawn Count", spawnCount, t1Stats?.spawn_count ?? null);
    }

    const rowH = 24;
    rows.forEach((row, i) => {
      const y = yStart + i * rowH;
      if (i % 2 === 0) this.ui.fillRect(contentX - 5, y - 2, contentW + 10, rowH, [20, 20, 32]);
      drawText(ctx, row.label, contentX, y, { size: CONTENT_FONT_SIZE, color: [160, 160, 180] });
      drawText(ctx, row.value, contentX + 160, y, { size: CONTENT_FONT_SIZE, color: CONTENT_TEXT });
      if (row.diff) {
        let better = row.diff.includes("+");
        if (row.lowerIsBetter) better = !better;
        drawText(ctx, row.diff, contentX + 160 + measure(ctx, row.value, CONTENT_FONT_SIZE), y, {
          size: CONTENT_FONT_SIZE,
          color: better ? DIFF_BETTER : DIFF_WORSE,
        });
      }
    });
    return yStart + rows.length * rowH;
  }

  private drawPassives(
    ctx: CanvasRenderingContext2D,
    passives: PassiveCard[],
    contentX: number,
    contentW: number,
    yStart: number,
  ): void {
    const pad = 8;
    let y = yStart;
    for (const card of passives) {
      const descLines = wrapText(ctx, card.desc, contentW - pad * 2 - 10, CONTENT_FONT_SIZE - 1);
      const cardH = pad * 2 + 20 + descLines.length * 16;

      this.ui.roundRectPath(contentX - 5, y, contentW + 10, cardH, 4);
      ctx.fillStyle = rgb([25, 25, 40]);
      ctx.fill();
      ctx.strokeStyle = rgb([60, 60, 85]);
      ctx.lineWidth = 1;
      ctx.stroke();

      drawText(ctx, card.name, contentX + pad, y + pad, {
        size: CONTENT_FONT_SIZE + 2,
        color: [220, 200, 120],
        bold: true,
      });
      descLines.forEach((line, j) => {
        drawText(ctx, line, contentX + pad, y + pad + 20 + j * 16, {
          size: CONTENT_FONT_SIZE - 1,
          color: [170, 170, 190],
        });
      });
      y += cardH + 8;
    }
  }
}

// -- helpers ------------------------------------------------------------------

function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
  size: number = CONTENT_FONT_SIZE,
): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const test = current ? `${current} ${word}` : word;
    if (measure(ctx, test, size) <= maxWidth) {
      current = test;
    } else {
      if (current) lines.push(current);
      current = word;
    }
  }
  if (current) lines.push(current);
  return lines.length ? lines : [""];
}
