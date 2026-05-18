import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TrafficLight } from "../TrafficLight";

describe("TrafficLight", () => {
  it("renders three circles", () => {
    const { container } = render(
      <TrafficLight probs={{ down: 0.2, neutral: 0.3, up: 0.5 }} />
    );
    const circles = container.querySelectorAll(".rounded-full");
    expect(circles.length).toBe(3);
  });

  it("shows labels when showLabels=true", () => {
    render(
      <TrafficLight probs={{ down: 0.2, neutral: 0.3, up: 0.5 }} showLabels />
    );
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("30%")).toBeInTheDocument();
    expect(screen.getByText("20%")).toBeInTheDocument();
  });

  it("applies glow to dominant direction (up)", () => {
    const { container } = render(
      <TrafficLight probs={{ down: 0.1, neutral: 0.1, up: 0.8 }} />
    );
    const upCircle = container.querySelector(".bg-green-500");
    expect(upCircle).toBeTruthy();
  });

  it("applies glow to dominant direction (down)", () => {
    const { container } = render(
      <TrafficLight probs={{ down: 0.7, neutral: 0.2, up: 0.1 }} />
    );
    const downCircle = container.querySelector(".bg-red-500");
    expect(downCircle).toBeTruthy();
  });
});
