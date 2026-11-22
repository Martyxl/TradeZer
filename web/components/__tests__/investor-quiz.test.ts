import { describe, expect, it } from "vitest";
import { quizPlan } from "@/components/investor/ui";

describe("quizPlan — dotazník investičního typu", () => {
  it("mapuje součet bodů na typ", () => {
    expect(quizPlan([3, 3, 3, 3])).toBe("aggressive");
    expect(quizPlan([2, 2, 2, 2])).toBe("bold");
    expect(quizPlan([1, 2, 1, 1])).toBe("balanced");
  });
  it("krátký horizont nebo panika typ omezí", () => {
    expect(quizPlan([0, 3, 3, 3])).toBe("careful");     // peníze do 3 let
    expect(quizPlan([3, 0, 3, 3])).toBe("careful");     // při propadu prodá
    expect(quizPlan([3, 1, 3, 3])).toBe("balanced");    // znervózní
  });
});
