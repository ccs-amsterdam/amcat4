import { AmcatUserRole } from "@/interfaces";
import { amcatUserRoles } from "@/schemas";
import { type ClassValue, clsx } from "clsx";
import {
  Bird,
  Bone,
  Bug,
  Cat,
  Dog,
  Egg,
  Fish,
  Origami,
  Panda,
  PawPrint,
  Rabbit,
  Rat,
  Shell,
  Shrimp,
  Snail,
  Squirrel,
  Turtle,
} from "lucide-react";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function hasMinAmcatRole(role: AmcatUserRole | undefined, minRole?: AmcatUserRole) {
  if (!minRole) return true;
  if (!role) return false;
  const roleIndex = amcatUserRoles.indexOf(role);
  const minRoleIndex = amcatUserRoles.indexOf(minRole);
  return roleIndex >= minRoleIndex;
}

export function randomLightColor(id: string) {
  const hash = simpleHash(id);
  const num1 = hash % 360; // 0-359 (for HUE)
  const num2 = (Math.floor(hash / 360) % 50) + 50; // 50-99 (for SATURATION)
  return `hsl(${num1}, ${num2}%, 85%)`;
}

export function randomIcon(id: string, className?: string) {
  const hash = simpleHash(id);
  const i = hash % funIcons.length;
  return funIcons[i];
}

const funIcons = [
  Bird,
  Bone,
  Bug,
  Cat,
  Dog,
  Egg,
  Fish,
  Origami,
  Panda,
  PawPrint,
  Rabbit,
  Rat,
  Shell,
  Shrimp,
  Snail,
  Squirrel,
  Turtle,
];

function simpleHash(str: string) {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    // hash * 33 + char_code (optimized as (hash << 5) + hash)
    hash = (hash << 5) + hash + str.charCodeAt(i);
    // Ensure it's a 32-bit positive integer
    hash = hash & hash;
  }
  return Math.abs(hash);
}
