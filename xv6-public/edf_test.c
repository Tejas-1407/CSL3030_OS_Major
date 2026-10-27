#include "types.h"
#include "stat.h"
#include "user.h"

#define NCHILDREN 3
#define WORK_ITERATIONS 20000000

int
main(int argc, char *argv[])
{
  int i, pid, children;
  int wids[NCHILDREN] = {1, 2, 3};
  uint deadlines[NCHILDREN] = {300, 100, 200};
  uint start_tick;

  start_tick = uptime() + 20;
  children = 0;
  for(i = 0; i < NCHILDREN; i++){
    pid = fork();
    if(pid < 0){
      printf(1, "edf_test: fork failed\n");
      break;
    }
    if(pid == 0){
      uint j, work;

      if(setworkflow(wids[i], deadlines[i]) < 0){
        printf(1, "edf_test: setworkflow failed\n");
        exit();
      }

      while((uint)uptime() < start_tick)
        sleep(1);

      work = 0;
      printf(1, "START pid=%d wid=%d deadline=%d\n",
             getpid(), wids[i], deadlines[i]);
      for(j = 0; j < WORK_ITERATIONS; j++)
        work = (work * 1664525) + j + 1013904223;
      printf(1, "FINISH pid=%d wid=%d deadline=%d work=%d\n",
             getpid(), wids[i], deadlines[i], work);
      exit();
    }
    children++;
  }

  for(i = 0; i < children; i++)
    wait();

  exit();
}
