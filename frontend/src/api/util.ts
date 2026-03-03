import { AmcatFilters, AmcatQuery, AmcatUserRole } from "@/interfaces";
import { amcatUserRoles } from "@/schemas";

export function addFilter(q: AmcatQuery, filters: AmcatFilters): AmcatQuery {
  const currentQueries = q.queries ?? [];
  const currentFilters = q.filters ?? {};
  return { queries: [...currentQueries], filters: { ...currentFilters, ...filters } };
}

export function roleHigherThan(role1: AmcatUserRole, role2: AmcatUserRole): boolean {
  const index1 = amcatUserRoles.indexOf(role1);
  const index2 = amcatUserRoles.indexOf(role2);
  return index1 > index2;
}

export function roleAtLeast(role1: AmcatUserRole, role2: AmcatUserRole): boolean {
  const index1 = amcatUserRoles.indexOf(role1);
  const index2 = amcatUserRoles.indexOf(role2);
  return index1 >= index2;
}

export function splitIntoBatches<T>(arr: T[], batchSize: number): T[][] {
  const batches: T[][] = [];
  for (let i = 0; i < arr.length; i += batchSize) {
    batches.push(arr.slice(i, i + batchSize));
  }
  return batches;
}
