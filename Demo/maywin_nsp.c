/*
 * maywin_nsp.c
 *
 * Nurse Scheduling Prototype (Weighted MILP).
 * Implements a small test model you can compile and run now.
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
 * Date: 10 Oct 2025
 *
 * This file follows Ajarn Sally's C coding standards
 * (file header, function headers, variable comments,
 * consistent indentation and braces). See reference.
 */

#include <stdio.h>
#include <stdlib.h>
#include "gurobi_c.h"

/* ---------------------- Defined constants (UPPER CASE) ---------------------- */
#define N_NURSES   20     /* number of nurses */
#define N_SHIFTS   3      /* 0 = Morning, 1 = Evening, 2 = Night */
#define N_DAYS     14     /* number of days in horizon */

/* Weights for objective terms (tune later) */
#define W1_COST    5.0
#define W2_FAIR    8.0
#define W3_PREF    6.0

/* Shift indices for rest rule example */
#define SHIFT_MORNING  0
#define SHIFT_NIGHT    2

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

/* ---------------------- Problem data (toy initializers) --------------------- */
/* Availability: a[nurse][day] in {0,1} */
static int availability[N_NURSES][N_DAYS];

/* Coverage requirement: r[shift][day] */
static int req_cover[N_SHIFTS][N_DAYS];

/* Cost per assignment: cost[nurse][shift][day] */
static double assign_cost[N_NURSES][N_SHIFTS][N_DAYS];

/* Preference score in [0,1]: pref[nurse][shift] */
static double pref_score[N_NURSES][N_SHIFTS];

/* Workload bounds per nurse */
static int min_work[N_NURSES];
static int max_work[N_NURSES];

/* Average work target derived from total demand */
static double avg_work_target = 0.0;

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
      fprintf(stderr, "Gurobi error %d: %s\n",
              err, GRBgeterrormsg(env));
      if (model != NULL)
      {
         GRBfreemodel(model);
      }
      if (env != NULL)
      {
         GRBfreeenv(env);
      }
      exit(1);
   }
}

/* ---------------------- Data initialization --------------------------------- */
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
      /* Everyone available every day (toy) */
      for (day = 0; day < N_DAYS; day++)
      {
         availability[nurse][day] = 1; /* available */
      }

      /* Per-nurse workload bounds (tune later) */
      min_work[nurse] = 6;
      max_work[nurse] = 10;

      /* Simple preference profile */
      for (shift = 0; shift < N_SHIFTS; shift++)
      {
         if (shift == SHIFT_MORNING)
         {
            pref_score[nurse][shift] = 1.0;
         }
         else if (shift == 1)
         {
            pref_score[nurse][shift] = 0.6;
         }
         else
         {
            pref_score[nurse][shift] = 0.3;
         }
      }
   }

   /* Coverage requirements: nights lighter staffing */
   for (shift = 0; shift < N_SHIFTS; shift++)
   {
      for (day = 0; day < N_DAYS; day++)
      {
         if (shift == SHIFT_NIGHT)
         {
            req_cover[shift][day] = 3;
         }
         else
         {
            req_cover[shift][day] = 5;
         }
         total_demand += req_cover[shift][day];
      }
   }

   /* Costs: nights costlier */
   for (nurse = 0; nurse < N_NURSES; nurse++)
   {
      for (shift = 0; shift < N_SHIFTS; shift++)
      {
         for (day = 0; day < N_DAYS; day++)
         {
            if (shift == SHIFT_NIGHT)
            {
               assign_cost[nurse][shift][day] = 2.0;
            }
            else
            {
               assign_cost[nurse][shift][day] = 1.0;
            }
         }
      }
   }

   /* Compute average work target from total demand */
   avg_work_target = ((double) total_demand) / (double) N_NURSES;
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
   int err = 0;                /* Gurobi error code */
   GRBmodel* model = NULL;     /* model handle */

   int n_x = N_NURSES * N_SHIFTS * N_DAYS;  /* number of x vars */
   int n_o = N_NURSES;                      /* number of o vars */
   int n_vars = n_x + n_o;                  /* total variables */

   double* obj = NULL;        /* objective coefficients */
   double* lb = NULL;         /* lower bounds */
   double* ub = NULL;         /* upper bounds */
   char* vtype = NULL;        /* variable types */

   int nurse = 0;             /* loop variables */
   int shift = 0;
   int day = 0;

   /* Allocate arrays for variables */
   obj = (double*) calloc(n_vars, sizeof(double));
   lb  = (double*) calloc(n_vars, sizeof(double));
   ub  = (double*) calloc(n_vars, sizeof(double));
   vtype = (char*) calloc(n_vars, sizeof(char));

   if ((obj == NULL) || (lb == NULL) || (ub == NULL) || (vtype == NULL))
   {
      fprintf(stderr, "Allocation failure in build_model\n");
      return 1;
   }

   /* Create empty model */
   err = GRBnewmodel(env, &model, "maywin_nsp",
                     0, NULL, NULL, NULL, NULL, NULL);
   die_if_error(err, env, model);

   /* ---------------- Variables: x (binary), with combined objective coeffs */
   for (nurse = 0; nurse < N_NURSES; nurse++)
   {
      for (shift = 0; shift < N_SHIFTS; shift++)
      {
         for (day = 0; day < N_DAYS; day++)
         {
            int idx = x_index(nurse, shift, day);

            vtype[idx] = GRB_BINARY;
            lb[idx] = 0.0;
            ub[idx] = 1.0;

            /* obj = W1*cost + W3*(1 - pref) */
            obj[idx] =
               (W1_COST * assign_cost[nurse][shift][day]) +
               (W3_PREF * (1.0 - pref_score[nurse][shift]));
         }
      }
   }

   /* ---------------- Variables: o (continuous >= 0), fairness weight */
   for (nurse = 0; nurse < N_NURSES; nurse++)
   {
      int idx = o_index(nurse);

      vtype[idx] = GRB_CONTINUOUS;
      lb[idx] = 0.0;
      ub[idx] = GRB_INFINITY;
      obj[idx] = W2_FAIR;
   }

   err = GRBaddvars(model, n_vars, 0, NULL, NULL, NULL,
                    obj, lb, ub, vtype, NULL);
   die_if_error(err, env, model);

   free(obj);
   free(lb);
   free(ub);
   free(vtype);

   /* ---------------- Constraint (1): Coverage sum_i x = r[shift][day] */
   for (shift = 0; shift < N_SHIFTS; shift++)
   {
      for (day = 0; day < N_DAYS; day++)
      {
         int nurse_count = N_NURSES; /* number of terms */
         int* ind = (int*) malloc(nurse_count * sizeof(int));
         double* val = (double*) malloc(nurse_count * sizeof(double));
         int i = 0; /* loop */

         if ((ind == NULL) || (val == NULL))
         {
            fprintf(stderr, "Allocation failure (coverage)\n");
            return 1;
         }

         for (nurse = 0; nurse < N_NURSES; nurse++)
         {
            ind[i] = x_index(nurse, shift, day);
            val[i] = 1.0;
            i = i + 1;
         }

         err = GRBaddconstr(model, nurse_count, ind, val,
                            GRB_EQUAL, (double) req_cover[shift][day],
                            "cover");
         die_if_error(err, env, model);

         free(ind);
         free(val);
      }
   }

   /* ---------------- Constraint (2): Availability x <= a */
   for (nurse = 0; nurse < N_NURSES; nurse++)
   {
      for (shift = 0; shift < N_SHIFTS; shift++)
      {
         for (day = 0; day < N_DAYS; day++)
         {
            int ind[1];
            double val[1];
            double rhs = (double) availability[nurse][day];

            ind[0] = x_index(nurse, shift, day);
            val[0] = 1.0;

            err = GRBaddconstr(model, 1, ind, val,
                               GRB_LESS_EQUAL, rhs, "avail");
            die_if_error(err, env, model);
         }
      }
   }

   /* ---------------- Constraint (3): One shift per day sum_j x <= 1 */
   for (nurse = 0; nurse < N_NURSES; nurse++)
   {
      for (day = 0; day < N_DAYS; day++)
      {
         int term_count = N_SHIFTS;
         int* ind = (int*) malloc(term_count * sizeof(int));
         double* val = (double*) malloc(term_count * sizeof(double));
         int j = 0; /* loop */

         if ((ind == NULL) || (val == NULL))
         {
            fprintf(stderr, "Allocation failure (one-per-day)\n");
            return 1;
         }

         for (shift = 0; shift < N_SHIFTS; shift++)
         {
            ind[j] = x_index(nurse, shift, day);
            val[j] = 1.0;
            j = j + 1;
         }

         err = GRBaddconstr(model, term_count, ind, val,
                            GRB_LESS_EQUAL, 1.0, "one_per_day");
         die_if_error(err, env, model);

         free(ind);
         free(val);
      }
   }

   /* ---------------- Constraint (4): Simple rest rule
    * Night_k + Morning_{k+1} <= 1
    */
   for (nurse = 0; nurse < N_NURSES; nurse++)
   {
      for (day = 0; day < (N_DAYS - 1); day++)
      {
         int ind[2];
         double val[2];

         ind[0] = x_index(nurse, SHIFT_NIGHT, day);
         ind[1] = x_index(nurse, SHIFT_MORNING, day + 1);
         val[0] = 1.0;
         val[1] = 1.0;

         err = GRBaddconstr(model, 2, ind, val,
                            GRB_LESS_EQUAL, 1.0, "rest");
         die_if_error(err, env, model);
      }
   }

   /* ---------------- Constraint (5): Workload bounds per nurse */
   for (nurse = 0; nurse < N_NURSES; nurse++)
   {
      int term_count = N_SHIFTS * N_DAYS;
      int* ind = (int*) malloc(term_count * sizeof(int));
      double* val = (double*) malloc(term_count * sizeof(double));
      int c = 0; /* counter */

      if ((ind == NULL) || (val == NULL))
      {
         fprintf(stderr, "Allocation failure (workload)\n");
         return 1;
      }

      for (shift = 0; shift < N_SHIFTS; shift++)
      {
         for (day = 0; day < N_DAYS; day++)
         {
            ind[c] = x_index(nurse, shift, day);
            val[c] = 1.0;
            c = c + 1;
         }
      }

      err = GRBaddconstr(model, term_count, ind, val,
                         GRB_LESS_EQUAL, (double) max_work[nurse],
                         "work_upper");
      die_if_error(err, env, model);

      err = GRBaddconstr(model, term_count, ind, val,
                         GRB_GREATER_EQUAL, (double) min_work[nurse],
                         "work_lower");
      die_if_error(err, env, model);

      free(ind);
      free(val);
   }

   /* ---------------- Constraint (6): Fairness link
    * sum_{j,k} x[i,j,k] - o[i] <= avg_work_target
    */
   for (nurse = 0; nurse < N_NURSES; nurse++)
   {
      int term_count = (N_SHIFTS * N_DAYS) + 1;
      int* ind = (int*) malloc(term_count * sizeof(int));
      double* val = (double*) malloc(term_count * sizeof(double));
      int c = 0; /* counter */

      if ((ind == NULL) || (val == NULL))
      {
         fprintf(stderr, "Allocation failure (fairness)\n");
         return 1;
      }

      for (shift = 0; shift < N_SHIFTS; shift++)
      {
         for (day = 0; day < N_DAYS; day++)
         {
            ind[c] = x_index(nurse, shift, day);
            val[c] = 1.0;
            c = c + 1;
         }
      }

      ind[c] = o_index(nurse);
      val[c] = -1.0;

      err = GRBaddconstr(model, term_count, ind, val,
                         GRB_LESS_EQUAL, avg_work_target, "fair_link");
      die_if_error(err, env, model);

      free(ind);
      free(val);
   }

   /* ---------------- Model sense: minimize ---------------- */
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
   int err = 0;                    /* Gurobi error code */
   int status = 0;                 /* optimization status */
   double obj_val = 0.0;           /* objective value */

   int var_count = 0;              /* total variable count */
   double* solution = NULL;        /* solution vector */

   int day = 0;                    /* loop variables */
   int shift = 0;
   int nurse = 0;

   err = GRBoptimize(model);
   die_if_error(err, env, model);

   err = GRBgetintattr(model, GRB_INT_ATTR_STATUS, &status);
   die_if_error(err, env, model);

   if ((status == GRB_OPTIMAL) || (status == GRB_SUBOPTIMAL))
   {
      err = GRBgetdblattr(model, GRB_DBL_ATTR_OBJVAL, &obj_val);
      die_if_error(err, env, model);

      err = GRBgetintattr(model, GRB_INT_ATTR_NUMVARS, &var_count);
      die_if_error(err, env, model);

      solution = (double*) malloc(var_count * sizeof(double));
      if (solution == NULL)
      {
         fprintf(stderr, "Allocation failure (solution)\n");
         return;
      }

      err = GRBgetdblattrarray(model, GRB_DBL_ATTR_X,
                               0, var_count, solution);
      die_if_error(err, env, model);

      printf("Objective value: %.4f\n", obj_val);

      for (day = 0; day < N_DAYS; day++)
      {
         printf("Day %d\n", day + 1);
         for (shift = 0; shift < N_SHIFTS; shift++)
         {
            int printed = 0; /* whether any nurse printed */
            printf("  Shift %d -> nurses: ", shift);
            for (nurse = 0; nurse < N_NURSES; nurse++)
            {
               int idx = x_index(nurse, shift, day);
               if (solution[idx] > 0.5)
               {
                  printf("%d ", nurse);
                  printed = 1;
               }
            }
            if (!printed)
            {
               printf("(none)");
            }
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
 * Creates environment, initializes data, builds model,
 * solves, prints results, and cleans up.
 */
int main(void)
{
   int err = 0;                  /* Gurobi error code */
   GRBenv* env = NULL;           /* Gurobi environment */
   GRBmodel* model = NULL;       /* model handle */

   /* Initialize toy data so the model runs end-to-end */
   init_toy_data();

   /* Create environment and set logging */
   err = GRBloadenv(&env, "maywin.log");
   die_if_error(err, env, model);

   /* Verbose output on for debugging; set to 0 if too chatty */
   err = GRBsetintparam(env, GRB_INT_PAR_OUTPUTFLAG, 1);
   die_if_error(err, env, model);

   /* Build model */
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
