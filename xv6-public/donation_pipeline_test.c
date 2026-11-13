#include "types.h"
#include "stat.h"
#include "user.h"

#define NHOG 4
#define NSTAGES 4
#define NCHILDREN 5
#define STAGE_WORK 100000

struct completion {
  uint tick;
};

static void
close_child(int id, int readyfd[2], int work_gate[2])
{
  close(readyfd[0]);
  close(work_gate[1]);
  if(id != 0 && id != NHOG)
    close(work_gate[0]);
}

static void
close_data(int id, int p12[2], int p23[2], int p34[2])
{
  if(id != 1)
    close(p12[0]);
  if(id != 0)
    close(p12[1]);
  if(id != 2)
    close(p23[0]);
  if(id != 1)
    close(p23[1]);
  if(id != 3)
    close(p34[0]);
  if(id != 2)
    close(p34[1]);
}

static void
ready(int fd, char stage)
{
  if(write(fd, &stage, 1) != 1)
    exit();
}

static void
work(uint *value)
{
  uint i;

  for(i = 0; i < STAGE_WORK; i++)
    *value = *value * 1664525U + i + 1013904223U;
}

static void
run_stage(int id, uint base, int p12[2], int p23[2], int p34[2],
          int readyfd, int work_gate[2])
{
  int inputfd, outputfd;
  uint value;
  char token;
  struct completion result;

  if(id == 0){
    if(setworkflow(1, base + 500) < 0)
      exit();
    printf(1, "PIPELINE_STAGE stage=1 pid=%d deadline=%d\n",
           getpid(), base + 500);
    value = 0x100;
    if(write(p12[1], &value, sizeof(value)) != sizeof(value))
      exit();
    ready(readyfd, 'A');
    if(read(work_gate[0], &token, 1) != 1)
      exit();
    work(&value);
    if(write(p12[1], &value, sizeof(value)) != sizeof(value))
      exit();
    close(p12[1]);
    close(readyfd);
    close(work_gate[0]);
    exit();
  }

  if(id == 1){
    inputfd = p12[0];
    outputfd = p23[1];
  } else if(id == 2){
    inputfd = p23[0];
    outputfd = p34[1];
  } else {
    inputfd = p34[0];
    outputfd = -1;
  }

  if(setworkflow(1, base + (id == 1 ? 400 : id == 2 ? 300 : 100)) < 0)
    exit();
  printf(1, "PIPELINE_STAGE stage=%d pid=%d deadline=%d\n", id + 1,
         getpid(), base + (id == 1 ? 400 : id == 2 ? 300 : 100));
  if(read(inputfd, &value, sizeof(value)) != sizeof(value))
    exit();
  if(outputfd >= 0){
    value = 0x200 + id;
    if(write(outputfd, &value, sizeof(value)) != sizeof(value))
      exit();
  }
  ready(readyfd, id == 1 ? 'B' : id == 2 ? 'C' : 'D');
  if(read(inputfd, &value, sizeof(value)) != sizeof(value))
    exit();
  work(&value);
  if(outputfd >= 0){
    if(write(outputfd, &value, sizeof(value)) != sizeof(value))
      exit();
    close(outputfd);
  } else {
    result.tick = uptime();
    if(write(readyfd, &result, sizeof(result)) != sizeof(result))
      exit();
  }
  close(inputfd);
  close(readyfd);
  exit();
}

static void
run_hog(int readyfd, int work_gate[2], uint base)
{
  uint value;
  char token;

  if(setworkflow(2, base + 150) < 0)
    exit();
  printf(1, "PIPELINE_HOG pid=%d deadline=%d\n", getpid(), base + 150);
  ready(readyfd, 'H');
  if(read(work_gate[0], &token, 1) != 1)
    exit();
  close(work_gate[0]);
  close(readyfd);
  value = 1;
  while((uint)uptime() < base + 150)
    value = value * 1664525U + 1013904223U;
  if(value == 0)
    printf(1, "PIPELINE_HOG checksum=0\n");
  exit();
}

int
main(void)
{
  int p12[2], p23[2], p34[2];
  int readyfd[2], work_gate[2];
  int pids[NCHILDREN], id, child, i;
  uint base;
  char token;
  struct completion result;
  uint release_tick;
  int elapsed, deadline_ticks, miss;

  if(pipe(p12) < 0 || pipe(p23) < 0 || pipe(p34) < 0 ||
     pipe(readyfd) < 0 || pipe(work_gate) < 0){
    printf(2, "donation_pipeline_test: pipe creation failed\n");
    exit();
  }
  base = (uint)uptime() + 100;

  for(id = 0; id < NCHILDREN; id++){
    child = fork();
    if(child < 0){
      printf(2, "donation_pipeline_test: fork failed\n");
      exit();
    }
    if(child == 0){
      close_child(id, readyfd, work_gate);
      close_data(id, p12, p23, p34);
      if(id == NHOG)
        run_hog(readyfd[1], work_gate, base);
      run_stage(id, base, p12, p23, p34, readyfd[1], work_gate);
      exit();
    }
    pids[id] = child;
    if(read(readyfd[0], &token, 1) != 1){
      printf(2, "donation_pipeline_test: stage setup failed\n");
      exit();
    }
  }

  close(readyfd[1]);
  close(work_gate[0]);
  close(p12[0]);
  close(p12[1]);
  close(p23[0]);
  close(p23[1]);
  close(p34[0]);
  close(p34[1]);

  while((uint)uptime() < base)
    ;
  release_tick = (uint)uptime();
  token = 'w';
  if(write(work_gate[1], &token, 1) != 1 ||
     write(work_gate[1], &token, 1) != 1){
    printf(2, "donation_pipeline_test: release failed\n");
    exit();
  }
  close(work_gate[1]);

  for(i = 0; i < NCHILDREN; i++){
    if(wait() < 0){
      printf(2, "donation_pipeline_test: wait failed\n");
      exit();
    }
  }
  if(read(readyfd[0], &result, sizeof(result)) != sizeof(result)){
    printf(2, "donation_pipeline_test: workflow result missing\n");
    exit();
  }
  close(readyfd[0]);

  elapsed = (int)(result.tick - release_tick);
  deadline_ticks = (int)(base + 100 - release_tick);
  miss = elapsed > deadline_ticks;
  printf(1, "BENCH_RESULT wid=1 stages=%d elapsed=%d deadline=%d miss=%d\n",
         NSTAGES, elapsed, deadline_ticks, miss);
  printf(1, "BENCH_SUMMARY workflows=1 completed=1 deadline_misses=%d\n",
         miss);
  printf(1, "donation_pipeline_test: complete pids=%d,%d,%d,%d hog=%d\n",
         pids[0], pids[1], pids[2], pids[3], pids[NHOG]);
  exit();
}
