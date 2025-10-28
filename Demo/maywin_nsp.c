/*
 * maywin_nsp.c
 *
 * Nurse Scheduling Prototype (Weighted MILP) with CSV input support.
 * - Objective:
 *     Minimize  w1 * sum(c[i,j,k] * x[i,j,k])
 *             + w2 * sum(o[i])
 *             + w3 * sum((1 - pref[i,j]) * x[i,j,k])
 * - Constraints:
 *     (1) Coverage            sum_i x[i,j,k] = r[j,k]
 *     (2) Availability        x[i,j,k] <= a[i,k]
 *     (3) One-per-day         sum_j x[i,j,k] <= 1
 *     (4) Rest example        Night_k + Morning_{k+1] <= 1
 *     (5) Workload bounds     minW[i] <= sum x[i,*,*] <= maxW[i]
 *     (6) Fairness link       sum x[i,*,*] - o[i] <= avgWork
 *
 * Created by: Chirayu Sukhum (Tuey)
 * Date: 10 Oct 2025 (revised to add CSV I/O & inspectors)
 *
 * This file follows Ajarn Sally's C coding standards
 * (file header, function headers, variable comments,
 * consistent indentation and braces).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include "gurobi_c.h"

/* ---------------------- Runtime sizes (loaded or toy) ----------------------- */
static int N_NURSES = 0;   /* number of nurses */
static int N_SHIFTS = 0;   /* 0 = Morning, 1 = Evening, 2 = Night (typical) */
static int N_DAYS   = 0;   /* horizon length in days */

/* Weights for objective terms (tune later) */
#define W1_COST    5.0
#define W2_FAIR    8.0
#define W3_PREF    6.0

/* Shift indices for rest rule example */
#define SHIFT_MORNING  0
#define SHIFT_NIGHT    2

/* ---------------------- Problem data (now dynamic) -------------------------- */
/* Availability: a[nurse][day] in {0,1} */
static int    **availability = NULL;       /* [N_NURSES][N_DAYS] */

/* Coverage requirement: r[shift][day] */
static int    **req_cover = NULL;          /* [N_SHIFTS][N_DAYS] */

/* Cost per assignment: cost[nurse][shift][day] */
static double ***assign_cost = NULL;       /* [N_NURSES][N_SHIFTS][N_DAYS] */

/* Preference score in [0,1]: pref[nurse][shift] */
static double **pref_score = NULL;         /* [N_NURSES][N_SHIFTS] */

/* Workload bounds per nurse */
static int    *min_work = NULL;            /* [N_NURSES] */
static int    *max_work = NULL;            /* [N_NURSES] */

/* Average work target derived from total demand */
static double avg_work_target = 0.0;

/* ---------------------- Indexing helpers (flatten 3D) ----------------------- */
/*
 * Convert (nurse, shift, day) to a single linear index for x variables.
 */
static inline int x_index(int nurse, int shift, int day)
{
  return (nurse * N_SHIFTS * N_DAYS) + (shift * N_DAYS) + day;
}

/*
 * Convert nurse index to linear index of o variables, which follow all x vars.
 */
static inline int o_index(int nurse)
{
  return (N_NURSES * N_SHIFTS * N_DAYS) + nurse;
}

/* ---------------------- Error handling helper ------------------------------- */
/*
 * If err != 0, print Gurobi message and exit.
 * Arguments:
 *   err   - Gurobi error code
 *   env   - Gurobi environment (may be NULL)
 *   model - Gurobi model (may be NULL)
 */
static void die_if_error(int err, GRBenv* env, GRBmodel* model)
{
  if (err != 0)
  {
    fprintf(stderr, "Gurobi error %d: %s\n", err, GRBgeterrormsg(env));
    if (model != NULL) GRBfreemodel(model);
    if (env   != NULL) GRBfreeenv(env);
    exit(1);
  }
}

/* ---------------------- Small CSV utilities -------------------------------- */
static char *trim(char *p)
{
  while (isspace((unsigned char)*p)) p++;
  if (*p == 0) return p;
  char *end = p + strlen(p) - 1;
  while (end > p && isspace((unsigned char)*end)) *end-- = 0;
  return p;
}

/* sizes.txt contains three ints: N_NURSES N_SHIFTS N_DAYS */
static int read_sizes(const char *path, int *n, int *s, int *d)
{
  FILE *fp = fopen(path, "r");
  if (!fp) { perror(path); return 1; }
  int ok = (fscanf(fp, "%d %d %d", n, s, d) == 3);
  fclose(fp);
  return ok ? 0 : 1;
}

/* Read rows x cols of ints from CSV into out[rows][cols] */
static int read_csv_int_matrix(const char *path, int rows, int cols, int **out)
{
  FILE *fp = fopen(path, "r");
  if (!fp) { perror(path); return 1; }

  char line[1<<15];
  int r = 0;
  while (r < rows && fgets(line, sizeof(line), fp))
  {
    char *p = trim(line);
    if (*p == 0 || *p == '#') continue;
    int c = 0;
    char *tok = strtok(p, ",");
    while (tok && c < cols)
    {
      out[r][c++] = atoi(trim(tok));
      tok = strtok(NULL, ",");
    }
    if (c != cols)
    {
      fclose(fp);
      fprintf(stderr, "%s: expected %d cols, got %d (row %d)\n", path, cols, c, r);
      return 1;
    }
    r++;
  }
  fclose(fp);
  if (r != rows)
  {
    fprintf(stderr, "%s: expected %d rows, got %d\n", path, rows, r);
    return 1;
  }
  return 0;
}

/* Read rows x cols of doubles from CSV into out[rows][cols] */
static int read_csv_double_matrix(const char *path, int rows, int cols, double **out)
{
  FILE *fp = fopen(path, "r");
  if (!fp) { perror(path); return 1; }

  char line[1<<15];
  int r = 0;
  while (r < rows && fgets(line, sizeof(line), fp))
  {
    char *p = trim(line);
    if (*p == 0 || *p == '#') continue;
    int c = 0;
    char *tok = strtok(p, ",");
    while (tok && c < cols)
    {
      out[r][c++] = atof(trim(tok));
      tok = strtok(NULL, ",");
    }
    if (c != cols)
    {
      fclose(fp);
      fprintf(stderr, "%s: expected %d cols, got %d (row %d)\n", path, cols, c, r);
      return 1;
    }
    r++;
  }
  fclose(fp);
  if (r != rows)
  {
    fprintf(stderr, "%s: expected %d rows, got %d\n", path, rows, r);
    return 1;
  }
  return 0;
}

/* ---------------------- Allocation helpers ---------------------------------- */
static int alloc_data_structs(void)
{
  int i, j;

  availability = (int**) malloc(N_NURSES * sizeof(int*));
  req_cover    = (int**) malloc(N_SHIFTS * sizeof(int*));
  pref_score   = (double**) malloc(N_NURSES * sizeof(double*));
  min_work     = (int*) malloc(N_NURSES * sizeof(int));
  max_work     = (int*) malloc(N_NURSES * sizeof(int));

  if (!availability || !req_cover || !pref_score || !min_work || !max_work)
    return 1;

  for (i = 0; i < N_NURSES; ++i)
  {
    availability[i] = (int*) malloc(N_DAYS * sizeof(int));
    pref_score[i]   = (double*) malloc(N_SHIFTS * sizeof(double));
    if (!availability[i] || !pref_score[i]) return 1;
  }

  for (j = 0; j < N_SHIFTS; ++j)
  {
    req_cover[j] = (int*) malloc(N_DAYS * sizeof(int));
    if (!req_cover[j]) return 1;
  }

  assign_cost = (double***) malloc(N_NURSES * sizeof(double**));
  if (!assign_cost) return 1;
  for (i = 0; i < N_NURSES; ++i)
  {
    assign_cost[i] = (double**) malloc(N_SHIFTS * sizeof(double*));
    if (!assign_cost[i]) return 1;
    for (j = 0; j < N_SHIFTS; ++j)
    {
      assign_cost[i][j] = (double*) malloc(N_DAYS * sizeof(double));
      if (!assign_cost[i][j]) return 1;
    }
  }
  return 0;
}

/* ---------------------- Input: load from files ------------------------------ */
/*
 * Files:
 *   sizes.txt           : N_NURSES N_SHIFTS N_DAYS
 *   availability.csv    : N_NURSES x N_DAYS (0/1)
 *   req_cover.csv       : N_SHIFTS x N_DAYS
 *   assign_cost.csv     : (N_NURSES*N_SHIFTS) x N_DAYS (row order: nurse-major, shift-minor)
 *   pref_score.csv      : N_NURSES x N_SHIFTS (0..1)
 *   work_bounds.csv     : N_NURSES x 2 (min,max)
 */
static int load_from_files(
  const char *sizes_path,
  const char *availability_path,
  const char *req_cover_path,
  const char *assign_cost_path,
  const char *pref_path,
  const char *work_bounds_path
)
{
  if (read_sizes(sizes_path, &N_NURSES, &N_SHIFTS, &N_DAYS))
  {
    fprintf(stderr, "Failed to read sizes from %s\n", sizes_path);
    return 1;
  }
  if (alloc_data_structs())
  {
    fprintf(stderr, "Allocation failed\n");
    return 1;
  }

  if (read_csv_int_matrix(availability_path, N_NURSES, N_DAYS, availability)) return 1;
  if (read_csv_int_matrix(req_cover_path,    N_SHIFTS, N_DAYS, req_cover))    return 1;
  if (read_csv_double_matrix(pref_path,      N_NURSES, N_SHIFTS, pref_score)) return 1;

  /* work_bounds: N_NURSES x 2 → split to min_work / max_work */
  {
    double **wb = (double**) malloc(N_NURSES * sizeof(double*));
    if (!wb) return 1;
    for (int i = 0; i < N_NURSES; ++i) wb[i] = (double*) malloc(2 * sizeof(double));
    if (read_csv_double_matrix(work_bounds_path, N_NURSES, 2, wb)) return 1;
    for (int i = 0; i < N_NURSES; ++i) { min_work[i] = (int) wb[i][0]; max_work[i] = (int) wb[i][1]; }
    for (int i = 0; i < N_NURSES; ++i) free(wb[i]); free(wb);
  }

  /* assign_cost: (N_NURSES*N_SHIFTS) x N_DAYS → map to 3D */
  {
    int rows = N_NURSES * N_SHIFTS;
    double **flat = (double**) malloc(rows * sizeof(double*));
    if (!flat) return 1;
    for (int r = 0; r < rows; ++r) flat[r] = (double*) malloc(N_DAYS * sizeof(double));
    if (read_csv_double_matrix(assign_cost_path, rows, N_DAYS, flat)) return 1;

    int r = 0;
    for (int i = 0; i < N_NURSES; ++i)
    {
      for (int s = 0; s < N_SHIFTS; ++s)
      {
        for (int d = 0; d < N_DAYS; ++d)
          assign_cost[i][s][d] = flat[r][d];
        r++;
      }
    }
    for (int rr = 0; rr < rows; ++rr) free(flat[rr]); free(flat);
  }

  /* compute avg_work_target from coverage */
  {
    int total = 0;
    for (int s = 0; s < N_SHIFTS; ++s)
      for (int d = 0; d < N_DAYS; ++d)
        total += req_cover[s][d];
    avg_work_target = ((double) total) / (double) N_NURSES;
  }

  return 0;
}

/* ---------------------- Data initialization (toy) --------------------------- */
/*
 * Initialize small toy data so the model can run without files.
 * Everyone is available; nights have lower staffing and higher cost;
 * simple preferences: Morning liked most.
 */
static void init_toy_data(void)
{
  int nurse = 0;      /* loop variable for nurses */
  int shift = 0;      /* loop variable for shifts */
  int day = 0;        /* loop variable for days */
  int total_demand = 0; /* total required assignments over horizon */

  for (nurse = 0; nurse < N_NURSES; nurse++)
  {
    for (day = 0; day < N_DAYS; day++)
    {
      availability[nurse][day] = 1; /* available */
    }

    min_work[nurse] = 6;
    max_work[nurse] = 10;

    for (shift = 0; shift < N_SHIFTS; shift++)
    {
      if (shift == SHIFT_MORNING)      pref_score[nurse][shift] = 1.0;
      else if (shift == 1)             pref_score[nurse][shift] = 0.6;
      else                              pref_score[nurse][shift] = 0.3;
    }
  }

  for (shift = 0; shift < N_SHIFTS; shift++)
  {
    for (day = 0; day < N_DAYS; day++)
    {
      if (shift == SHIFT_NIGHT) req_cover[shift][day] = 3;
      else                      req_cover[shift][day] = 5;
      total_demand += req_cover[shift][day];
    }
  }

  for (nurse = 0; nurse < N_NURSES; nurse++)
    for (shift = 0; shift < N_SHIFTS; shift++)
      for (day = 0; day < N_DAYS; day++)
        assign_cost[nurse][shift][day] = (shift == SHIFT_NIGHT) ? 2.0 : 1.0;

  avg_work_target = ((double) total_demand) / (double) N_NURSES;
}

/* ---------------------- Inspectors & CSV dumpers ---------------------------- */
static void print_int_matrix(const char *title, int rows, int cols, int **a, int max_rows)
{
  printf("\n%s (%d x %d)\n", title, rows, cols);
  int rlim = (max_rows > 0 && max_rows < rows) ? max_rows : rows;
  for (int i = 0; i < rlim; ++i)
  {
    printf("row %d: ", i);
    for (int j = 0; j < cols; ++j) printf("%d%s", a[i][j], (j+1<cols?",":""));
    printf("\n");
  }
  if (rlim < rows) printf("... (%d more rows hidden)\n", rows - rlim);
}

static void print_double_matrix(const char *title, int rows, int cols, double **a, int max_rows)
{
  printf("\n%s (%d x %d)\n", title, rows, cols);
  int rlim = (max_rows > 0 && max_rows < rows) ? max_rows : rows;
  for (int i = 0; i < rlim; ++i)
  {
    printf("row %d: ", i);
    for (int j = 0; j < cols; ++j) printf("%.3f%s", a[i][j], (j+1<cols?",":""));
    printf("\n");
  }
  if (rlim < rows) printf("... (%d more rows hidden)\n", rows - rlim);
}

static void print_assign_cost_slice(int nurse, int shift)
{
  printf("\nassign_cost for nurse %d, shift %d over %d days:\n", nurse, shift, N_DAYS);
  for (int d = 0; d < N_DAYS; ++d)
    printf("%.3f%s", assign_cost[nurse][shift][d], (d+1<N_DAYS?",":""));
  printf("\n");
}

static void print_summary_inputs(void)
{
  print_int_matrix("Availability [nurse x day]", N_NURSES, N_DAYS, availability, (N_NURSES < 8 ? 0 : 8));
  print_int_matrix("Coverage req_cover [shift x day]", N_SHIFTS, N_DAYS, req_cover, 0);
  print_double_matrix("Preferences pref_score [nurse x shift]", N_NURSES, N_SHIFTS, pref_score, (N_NURSES < 8 ? 0 : 8));

  printf("\nWork bounds per nurse (first 10):\n");
  for (int i = 0; i < N_NURSES && i < 10; ++i)
    printf("nurse %d: min=%d max=%d\n", i, min_work[i], max_work[i]);
  if (N_NURSES > 10) printf("... (%d more nurses hidden)\n", N_NURSES - 10);

  print_assign_cost_slice(0, 0);
  if (N_SHIFTS > 1) print_assign_cost_slice(0, 1);
  if (N_SHIFTS > 2) print_assign_cost_slice(0, 2);

  int total_demand = 0;
  for (int s = 0; s < N_SHIFTS; ++s)
    for (int d = 0; d < N_DAYS; ++d)
      total_demand += req_cover[s][d];

  printf("\nN_NURSES=%d  N_SHIFTS=%d  N_DAYS=%d\n", N_NURSES, N_SHIFTS, N_DAYS);
  printf("Total demand over horizon = %d\n", total_demand);
  printf("avg_work_target = %.3f\n", avg_work_target);
}

static int dump_int_csv(const char *path, int rows, int cols, int **a)
{
  FILE *fp = fopen(path, "w"); if (!fp) { perror(path); return 1; }
  for (int i = 0; i < rows; ++i)
  {
    for (int j = 0; j < cols; ++j) fprintf(fp, "%d%s", a[i][j], (j+1<cols?",":""));
    fputc('\n', fp);
  }
  fclose(fp); return 0;
}

static int dump_double_csv(const char *path, int rows, int cols, double **a)
{
  FILE *fp = fopen(path, "w"); if (!fp) { perror(path); return 1; }
  for (int i = 0; i < rows; ++i)
  {
    for (int j = 0; j < cols; ++j) fprintf(fp, "%.6f%s", a[i][j], (j+1<cols?",":""));
    fputc('\n', fp);
  }
  fclose(fp); return 0;
}

/* Dump (N_NURSES*N_SHIFTS) x N_DAYS view of assign_cost for Excel check */
static int dump_assign_cost_csv(const char *path)
{
  FILE *fp = fopen(path, "w"); if (!fp) { perror(path); return 1; }
  for (int i = 0; i < N_NURSES; ++i)
  {
    for (int s = 0; s < N_SHIFTS; ++s)
    {
      for (int d = 0; d < N_DAYS; ++d)
        fprintf(fp, "%.6f%s", assign_cost[i][s][d], (d+1<N_DAYS?",":""));
      fputc('\n', fp);
    }
  }
  fclose(fp); return 0;
}

/* ---------------------- Model building -------------------------------------- */
/*
 * Build the MILP in the provided Gurobi model:
 *   - Variables: x (binary), o (continuous >= 0)
 *   - Objective: set via variable objective coefficients
 *   - Constraints: coverage, availability, one-per-day, rest,
 *                  workload bounds, fairness link.
 * Returns 0 on success, non-zero on failure.
 */
static int build_model(GRBenv* env, GRBmodel** model_ptr)
{
  int err = 0;
  GRBmodel* model = NULL;

  int n_x = N_NURSES * N_SHIFTS * N_DAYS;
  int n_o = N_NURSES;
  int n_vars = n_x + n_o;

  double* obj = NULL;
  double* lb  = NULL;
  double* ub  = NULL;
  char*   vtype = NULL;

  /* Allocate arrays for variables */
  obj   = (double*) calloc(n_vars, sizeof(double));
  lb    = (double*) calloc(n_vars, sizeof(double));
  ub    = (double*) calloc(n_vars, sizeof(double));
  vtype = (char*)   calloc(n_vars, sizeof(char));
  if (!obj || !lb || !ub || !vtype) { fprintf(stderr, "Allocation failure in build_model\n"); return 1; }

  /* Create empty model */
  err = GRBnewmodel(env, &model, "maywin_nsp",
                    0, NULL, NULL, NULL, NULL, NULL);
  die_if_error(err, env, model);

  /* x variables */
  for (int nurse = 0; nurse < N_NURSES; nurse++)
    for (int shift = 0; shift < N_SHIFTS; shift++)
      for (int day = 0; day < N_DAYS; day++)
      {
        int idx = x_index(nurse, shift, day);
        vtype[idx] = GRB_BINARY;
        lb[idx] = 0.0;
        ub[idx] = 1.0;
        obj[idx] =
          (W1_COST * assign_cost[nurse][shift][day]) +
          (W3_PREF * (1.0 - pref_score[nurse][shift]));
      }

  /* o variables */
  for (int nurse = 0; nurse < N_NURSES; nurse++)
  {
    int idx = o_index(nurse);
    vtype[idx] = GRB_CONTINUOUS;
    lb[idx] = 0.0;
    ub[idx] = GRB_INFINITY;
    obj[idx] = W2_FAIR;
  }

  err = GRBaddvars(model, n_vars, 0, NULL, NULL, NULL, obj, lb, ub, vtype, NULL);
  die_if_error(err, env, model);

  free(obj); free(lb); free(ub); free(vtype);

  /* (1) Coverage */
  for (int shift = 0; shift < N_SHIFTS; shift++)
  {
    for (int day = 0; day < N_DAYS; day++)
    {
      int nurse_count = N_NURSES;
      int* ind = (int*) malloc(nurse_count * sizeof(int));
      double* val = (double*) malloc(nurse_count * sizeof(double));
      if (!ind || !val) { fprintf(stderr, "Allocation failure (coverage)\n"); return 1; }

      for (int i = 0; i < N_NURSES; i++) { ind[i] = x_index(i, shift, day); val[i] = 1.0; }

      err = GRBaddconstr(model, nurse_count, ind, val, GRB_EQUAL,
                         (double) req_cover[shift][day], "cover");
      die_if_error(err, env, model);
      free(ind); free(val);
    }
  }

  /* (2) Availability */
  for (int nurse = 0; nurse < N_NURSES; nurse++)
    for (int shift = 0; shift < N_SHIFTS; shift++)
      for (int day = 0; day < N_DAYS; day++)
      {
        int ind[1] = { x_index(nurse, shift, day) };
        double val[1] = { 1.0 };
        double rhs = (double) availability[nurse][day];

        err = GRBaddconstr(model, 1, ind, val, GRB_LESS_EQUAL, rhs, "avail");
        die_if_error(err, env, model);
      }

  /* (3) One shift per day */
  for (int nurse = 0; nurse < N_NURSES; nurse++)
  {
    for (int day = 0; day < N_DAYS; day++)
    {
      int term_count = N_SHIFTS;
      int* ind = (int*) malloc(term_count * sizeof(int));
      double* val = (double*) malloc(term_count * sizeof(double));
      if (!ind || !val) { fprintf(stderr, "Allocation failure (one-per-day)\n"); return 1; }

      for (int j = 0; j < N_SHIFTS; j++) { ind[j] = x_index(nurse, j, day); val[j] = 1.0; }

      err = GRBaddconstr(model, term_count, ind, val, GRB_LESS_EQUAL, 1.0, "one_per_day");
      die_if_error(err, env, model);
      free(ind); free(val);
    }
  }

  /* (4) Rest rule: Night_k + Morning_{k+1} <= 1 */
  if (SHIFT_NIGHT < N_SHIFTS && SHIFT_MORNING < N_SHIFTS)
  {
    for (int nurse = 0; nurse < N_NURSES; nurse++)
    {
      for (int day = 0; day < (N_DAYS - 1); day++)
      {
        int ind[2] = { x_index(nurse, SHIFT_NIGHT, day), x_index(nurse, SHIFT_MORNING, day + 1) };
        double val[2] = { 1.0, 1.0 };

        err = GRBaddconstr(model, 2, ind, val, GRB_LESS_EQUAL, 1.0, "rest");
        die_if_error(err, env, model);
      }
    }
  }

  /* (5) Workload bounds per nurse */
  for (int nurse = 0; nurse < N_NURSES; nurse++)
  {
    int term_count = N_SHIFTS * N_DAYS;
    int* ind = (int*) malloc(term_count * sizeof(int));
    double* val = (double*) malloc(term_count * sizeof(double));
    if (!ind || !val) { fprintf(stderr, "Allocation failure (workload)\n"); return 1; }

    int c = 0;
    for (int shift = 0; shift < N_SHIFTS; shift++)
      for (int day = 0; day < N_DAYS; day++)
      {
        ind[c] = x_index(nurse, shift, day);
        val[c] = 1.0;
        c++;
      }

    err = GRBaddconstr(model, term_count, ind, val, GRB_LESS_EQUAL, (double) max_work[nurse], "work_upper");
    die_if_error(err, env, model);
    err = GRBaddconstr(model, term_count, ind, val, GRB_GREATER_EQUAL, (double) min_work[nurse], "work_lower");
    die_if_error(err, env, model);

    free(ind); free(val);
  }

  /* (6) Fairness link: sum_{j,k} x[i,j,k] - o[i] <= avg_work_target */
  for (int nurse = 0; nurse < N_NURSES; nurse++)
  {
    int term_count = (N_SHIFTS * N_DAYS) + 1;
    int* ind = (int*) malloc(term_count * sizeof(int));
    double* val = (double*) malloc(term_count * sizeof(double));
    if (!ind || !val) { fprintf(stderr, "Allocation failure (fairness)\n"); return 1; }

    int c = 0;
    for (int shift = 0; shift < N_SHIFTS; shift++)
      for (int day = 0; day < N_DAYS; day++)
      {
        ind[c] = x_index(nurse, shift, day);
        val[c] = 1.0;
        c++;
      }
    ind[c] = o_index(nurse);
    val[c] = -1.0;

    err = GRBaddconstr(model, term_count, ind, val, GRB_LESS_EQUAL, avg_work_target, "fair_link");
    die_if_error(err, env, model);

    free(ind); free(val);
  }

  err = GRBsetintattr(model, GRB_INT_ATTR_MODELSENSE, GRB_MINIMIZE);
  die_if_error(err, env, model);

  *model_ptr = model;
  return 0;
}

/* ---------------------- Solve and print solution ---------------------------- */
/*
 * Optimize the model and print a small roster preview.
 * Shows nurses assigned to each shift per day.
 */
static void solve_and_print(GRBenv* env, GRBmodel* model)
{
  int err = 0;
  int status = 0;
  double obj_val = 0.0;

  int var_count = 0;
  double* solution = NULL;

  err = GRBoptimize(model);
  die_if_error(err, env, model);

  err = GRBgetintattr(model, GRB_INT_ATTR_STATUS, &status);
  die_if_error(err, env, model);

  if (status == GRB_OPTIMAL || status == GRB_SUBOPTIMAL)
  {
    err = GRBgetdblattr(model, GRB_DBL_ATTR_OBJVAL, &obj_val);
    die_if_error(err, env, model);

    err = GRBgetintattr(model, GRB_INT_ATTR_NUMVARS, &var_count);
    die_if_error(err, env, model);

    solution = (double*) malloc(var_count * sizeof(double));
    if (!solution) { fprintf(stderr, "Allocation failure (solution)\n"); return; }

    err = GRBgetdblattrarray(model, GRB_DBL_ATTR_X, 0, var_count, solution);
    die_if_error(err, env, model);

    printf("\n================= SOLUTION =================\n");
    printf("Objective value: %.4f\n", obj_val);

    for (int day = 0; day < N_DAYS; day++)
    {
      printf("Day %d\n", day + 1);
      for (int shift = 0; shift < N_SHIFTS; shift++)
      {
        int printed = 0;
        printf("  Shift %d -> nurses: ", shift);
        for (int nurse = 0; nurse < N_NURSES; nurse++)
        {
          int idx = x_index(nurse, shift, day);
          if (solution[idx] > 0.5) { printf("%d ", nurse); printed = 1; }
        }
        if (!printed) printf("(none)");
        printf("\n");
      }
    }

    free(solution);
  }
  else
  {
    printf("Optimization ended with status = %d\n", status);
  }
}

/* ---------------------- Main ------------------------------------------------ */
/*
 * Program entry point.
 * Creates environment, initializes data (from CSV or toy),
 * prints input summary, builds model, solves, prints results, and cleans up.
 *
 * Usage:
 *   maywin_nsp.exe sizes.txt availability.csv req_cover.csv assign_cost.csv pref_score.csv work_bounds.csv
 *   (or) maywin_nsp.exe   # uses toy data
 */
int main(int argc, char **argv)
{
  int err = 0;
  GRBenv* env = NULL;
  GRBmodel* model = NULL;

  if (argc == 7)
  {
    /* Load from files */
    if (load_from_files(argv[1], argv[2], argv[3], argv[4], argv[5], argv[6]))
    {
      fprintf(stderr, "Failed to load input files.\n");
      return 1;
    }
  }
  else
  {
    /* Fallback: toy demo to keep end-to-end runnable */
    N_NURSES = 20; N_SHIFTS = 3; N_DAYS = 14;
    if (alloc_data_structs()) { fprintf(stderr, "Allocation failed\n"); return 1; }
    init_toy_data();
  }

  /* Show what the model is actually using */
  print_summary_inputs();

  /* Optional: write debug CSVs for Excel cross-check */
  dump_int_csv("debug_availability.csv", N_NURSES, N_DAYS, availability);
  dump_int_csv("debug_req_cover.csv",    N_SHIFTS, N_DAYS, req_cover);
  dump_double_csv("debug_pref_score.csv",N_NURSES, N_SHIFTS, pref_score);
  dump_assign_cost_csv("debug_assign_cost.csv");
  {
    FILE *fp = fopen("debug_work_bounds.csv", "w");
    if (fp) {
      for (int i=0;i<N_NURSES;++i) fprintf(fp, "%d,%d\n", min_work[i], max_work[i]);
      fclose(fp);
    }
  }
  printf("\nWrote debug_*.csv files for validation.\n");

  /* Gurobi environment & model */
  err = GRBloadenv(&env, "maywin.log");
  die_if_error(err, env, model);

  err = GRBsetintparam(env, GRB_INT_PAR_OUTPUTFLAG, 1);
  die_if_error(err, env, model);

  err = build_model(env, &model);
  if (err != 0)
  {
    fprintf(stderr, "Model build failed\n");
    GRBfreeenv(env);
    return 1;
  }

  /* Solve and print a small schedule preview */
  solve_and_print(env, model);

  /* Cleanup */
  GRBfreemodel(model);
  GRBfreeenv(env);

  return 0;
}
