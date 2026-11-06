import { describe, expect, it } from "vitest";
import { filterByCollection, itemEditable, validFilter } from "./collections";

const items = [{ id: "a", collection_id: "c1" }, { id: "b", collection_id: null }, { id: "c" }, { id: "d", collection_id: "c2" }];

describe("filterByCollection", () => {
  it("all devolve tudo", () => expect(filterByCollection(items, "all")).toHaveLength(4));
  it("none devolve só os sem coleção (null ou ausente)", () => expect(filterByCollection(items, "none").map((i) => i.id)).toEqual(["b", "c"]));
  it("id devolve só os da coleção", () => expect(filterByCollection(items, "c1").map((i) => i.id)).toEqual(["a"]));
});

describe("validFilter", () => {
  it("mantém filtros válidos e volta a all quando a coleção sumiu", () => {
    expect(validFilter("none", [])).toBe("none");
    expect(validFilter("c1", ["c1"])).toBe("c1");
    expect(validFilter("c9", ["c1"])).toBe("all");
  });
});

describe("itemEditable", () => {
  it("exige o papel E que o item permita", () => {
    expect(itemEditable(true, {})).toBe(true);
    expect(itemEditable(true, { can_edit: false })).toBe(false);
    expect(itemEditable(false, { can_edit: true })).toBe(false);
  });
});
