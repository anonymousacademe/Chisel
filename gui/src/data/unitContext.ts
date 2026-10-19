import { createContext, useContext } from "react";

/** The open project's unit word (scene / chapter / section); "scene" outside a project. Wording only. */
export const UnitContext = createContext<string>("scene");

export const useUnit = (): string => useContext(UnitContext);
