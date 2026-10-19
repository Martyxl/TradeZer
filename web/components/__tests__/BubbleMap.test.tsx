import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { BubbleMap, cluster, type OverviewItem } from "../valuation/BubbleMap";

const item = (ticker: string, pe: number, g: number, mc = 1e9): OverviewItem => ({
  ticker, name: `${ticker} Inc`, group_key: null, pctile_pe_fwd: pe, eps_growth_ntm: g,
  market_cap: mc, valuation_score: 50, composite_score: 60, valuation_verdict: "FÉROVÁ",
  horizon_verdict: null, bubble_flag: false, confidence: 0.9,
});

describe("BubbleMap shlukování", () => {
  it("vzdálené bubliny zůstanou samostatné", () => {
    const pts = [item("A", 10, 0), item("B", 90, 40)].map((it, i) => ({ it, cx: i * 300, cy: 100, r: 10 }));
    expect(cluster(pts).map((c) => c.members.length)).toEqual([1, 1]);
  });

  it("překrývající se se sloučí a klik ukáže seznam s odkazy", () => {
    const onSelect = vi.fn();
    render(<BubbleMap onSelect={onSelect}
      items={[item("SOFI", 50, 20), item("BBVA", 50.2, 20.1), item("BDX", 50.1, 19.9), item("FAR", 5, -10)]} />);
    const cl = screen.getAllByTestId("bubble-cluster");
    expect(cl).toHaveLength(1);
    expect(screen.queryByTestId("cluster-list")).toBeNull();
    fireEvent.click(cl[0]);
    expect(screen.getByTestId("cluster-list")).toBeTruthy();
    fireEvent.click(screen.getByText("SOFI Inc"));
    expect(onSelect).toHaveBeenCalledWith("SOFI");
  });
});
