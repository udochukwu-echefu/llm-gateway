"use client";
import { Children, cloneElement, isValidElement, type ReactNode, type ReactElement } from "react";
import { useListQuery } from "./use-list-query";
import { pico } from "@/lib/money";
import { PageCount } from "./list-controls";
type Element = ReactElement<{
  children?: ReactNode;
  value?: unknown;
  className?: string;
  "aria-sort"?: "ascending" | "descending" | "none";
}>;
function text(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(text).join(" ");
  if (isValidElement(node)) {
    const element = node as Element;
    if (element.props.value != null) return String(element.props.value);
    return text(element.props.children);
  }
  return "";
}
export function SortableTable({
  children,
  name,
  className,
}: {
  children: ReactNode;
  name: string;
  className?: string;
}) {
  const { params, set } = useListQuery();
  const index = Number(params.get(`${name}_sort`) ?? -1);
  const direction = params.get(`${name}_direction`) ?? "asc";
  const body = Children.toArray(children).find(
    (node) => isValidElement(node) && node.type === "tbody",
  ) as Element | undefined;
  const count = Children.toArray(body?.props.children).length;
  const parts = Children.toArray(children).map((part) => {
    if (!isValidElement(part)) return part;
    const element = part as Element;
    if (element.type === "thead")
      return cloneElement(
        element,
        {},
        Children.map(element.props.children, (row) => {
          if (!isValidElement(row)) return row;
          return cloneElement(
            row as Element,
            {},
            Children.map((row as Element).props.children, (heading, column) => {
              if (!isValidElement(heading)) return heading;
              return cloneElement(
                heading as Element,
                {
                  "aria-sort":
                    index === column ? (direction === "asc" ? "ascending" : "descending") : "none",
                },
                <button
                  className="sort-heading"
                  onClick={() =>
                    set({
                      [`${name}_sort`]: String(column),
                      [`${name}_direction`]:
                        index === column && direction === "asc" ? "desc" : "asc",
                    })
                  }
                >
                  {(heading as Element).props.children} ↕
                </button>,
              );
            }),
          );
        }),
      );
    if (element.type === "tbody") {
      const rows = Children.toArray(element.props.children);
      if (index >= 0)
        rows.sort((left, right) => {
          const value = (row: ReactNode) =>
            isValidElement(row)
              ? text(Children.toArray((row as Element).props.children)[index])
              : "";
          const a = value(left),
            b = value(right);
          const decimal = /^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/;
          const result =
            decimal.test(a) && decimal.test(b)
              ? pico(a) === pico(b)
                ? 0
                : pico(a) < pico(b)
                  ? -1
                  : 1
              : a.localeCompare(b, "en", { numeric: true });
          return direction === "desc" ? -result : result;
        });
      return cloneElement(element, {}, rows);
    }
    return element;
  });
  return (
    <>
      <div className="table-scroll">
        <table className={className}>{parts}</table>
      </div>
      <PageCount shown={count} total={count} />
    </>
  );
}
