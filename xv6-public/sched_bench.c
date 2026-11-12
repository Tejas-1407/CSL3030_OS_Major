#include "types.h"
#include "stat.h"
#include "user.h"

#define NFLOWS 3
#define STAGE_DEADLINE_STEP 1

struct bench_result {
  int wid;
  int stage;
  uint elapsed;
  int status;
  uint checksum;
};

static int
read_full(int fd, void *buf, int n)
{
  int total, count;

  total = 0;
  while(total < n){
    count = read(fd, (char*)buf + total, n - total);
    if(count < 0)
      return -1;
    if(count == 0)
      return total == 0 ? 0 : -1;
    total += count;
  }
  return 1;
}

static int
write_full(int fd, void *buf, int n)
{
  int total, count;

  total = 0;
  while(total < n){
    count = write(fd, (char*)buf + total, n - total);
    if(count <= 0)
      return -1;
    total += count;
  }
  return 0;
}

static void
report_result(int resultfd, int wid, int stage, int status,
              uint elapsed, uint checksum)
{
  struct bench_result result;

  result.wid = wid;
  result.stage = stage;
  result.elapsed = elapsed;
  result.status = status;
  result.checksum = checksum;
  write_full(resultfd, &result, sizeof(result));
}

static void
run_stage(int stage, int stages, int wid, int iterations, int deadline,
          int inputfd, int edgefd[2], int releasefd[2], int readyfd[2],
          int resultfd[2])
{
  int read_result;
  uint release_tick, process_deadline, value, i;
  struct bench_result result;

  close(releasefd[1]);
  close(readyfd[0]);
  close(resultfd[0]);
  if(edgefd[0] >= 0)
    close(edgefd[0]);

  if(inputfd >= 0){
    read_result = read_full(inputfd, &value, sizeof(value));
    if(read_result != 1){
      report_result(resultfd[1], wid, stage, -1, 0, 0);
      close(inputfd);
      if(edgefd[1] >= 0)
        close(edgefd[1]);
      close(readyfd[1]);
      close(releasefd[0]);
      close(resultfd[1]);
      exit();
    }
  }
  if(edgefd[1] >= 0){
    value = 0;
    if(write_full(edgefd[1], &value, sizeof(value)) < 0){
      report_result(resultfd[1], wid, stage, -1, 0, 0);
      if(inputfd >= 0)
        close(inputfd);
      close(edgefd[1]);
      close(readyfd[1]);
      close(releasefd[0]);
      close(resultfd[1]);
      exit();
    }
  }
  value = 'r';
  if(write_full(readyfd[1], &value, 1) < 0){
    report_result(resultfd[1], wid, stage, -1, 0, 0);
    if(inputfd >= 0)
      close(inputfd);
    if(edgefd[1] >= 0)
      close(edgefd[1]);
    close(readyfd[1]);
    close(releasefd[0]);
    close(resultfd[1]);
    exit();
  }
  close(readyfd[1]);

  read_result = read_full(releasefd[0], &release_tick, sizeof(release_tick));
  close(releasefd[0]);
  if(read_result != 1){
    report_result(resultfd[1], wid, stage, -1, 0, 0);
    if(inputfd >= 0)
      close(inputfd);
    if(edgefd[1] >= 0)
      close(edgefd[1]);
    close(resultfd[1]);
    exit();
  }

  process_deadline = release_tick + (uint)deadline +
                     (uint)(stages - stage - 1) * STAGE_DEADLINE_STEP;
  if(setworkflow(wid, process_deadline) < 0){
    report_result(resultfd[1], wid, stage, -1, 0, 0);
    if(inputfd >= 0)
      close(inputfd);
    if(edgefd[1] >= 0)
      close(edgefd[1]);
    close(resultfd[1]);
    exit();
  }

  while((uint)uptime() < release_tick)
    sleep(1);

  if(inputfd >= 0){
    read_result = read_full(inputfd, &value, sizeof(value));
    close(inputfd);
    if(read_result != 1){
      report_result(resultfd[1], wid, stage, -1, 0, 0);
      if(edgefd[1] >= 0)
        close(edgefd[1]);
      close(resultfd[1]);
      exit();
    }
  } else {
    value = (uint)wid;
  }

  for(i = 0; i < (uint)iterations; i++)
    value = value * 1664525U + i + 1013904223U;

  if(stage + 1 < stages){
    if(write_full(edgefd[1], &value, sizeof(value)) < 0)
      report_result(resultfd[1], wid, stage, -1, 0, value);
    close(edgefd[1]);
  } else {
    result.wid = wid;
    result.stage = stage;
    result.elapsed = (uint)uptime() - release_tick;
    result.status = 1;
    result.checksum = value;
    write_full(resultfd[1], &result, sizeof(result));
  }

  close(resultfd[1]);
  exit();
}

int
main(int argc, char *argv[])
{
  int stages, iterations, deadlines[NFLOWS];
  int releasefd[2], readyfd[2], resultfd[2];
  int child_count, flow, stage, pid, inputfd, edgefd[2];
  int completed, misses, errors, read_result, i;
  uint release_tick;
  struct bench_result result;

  if(argc != 6){
    printf(2, "usage: sched_bench stages work_iterations deadline1 deadline2 deadline3\n");
    exit();
  }

  stages = atoi(argv[1]);
  iterations = atoi(argv[2]);
  deadlines[0] = atoi(argv[3]);
  deadlines[1] = atoi(argv[4]);
  deadlines[2] = atoi(argv[5]);
  if((stages != 2 && stages != 4 && stages != 8) || iterations <= 0 ||
     deadlines[0] <= 0 || deadlines[1] <= 0 || deadlines[2] <= 0){
    printf(2, "sched_bench: stages must be 2, 4, or 8; work and deadlines must be positive\n");
    exit();
  }

  if(pipe(releasefd) < 0){
    printf(2, "sched_bench: pipe creation failed\n");
    exit();
  }
  if(pipe(readyfd) < 0){
    close(releasefd[0]);
    close(releasefd[1]);
    printf(2, "sched_bench: pipe creation failed\n");
    exit();
  }
  if(pipe(resultfd) < 0){
    close(releasefd[0]);
    close(releasefd[1]);
    close(readyfd[0]);
    close(readyfd[1]);
    printf(2, "sched_bench: pipe creation failed\n");
    exit();
  }

  child_count = 0;
  for(flow = 0; flow < NFLOWS; flow++){
    inputfd = -1;
    for(stage = 0; stage < stages; stage++){
      edgefd[0] = -1;
      edgefd[1] = -1;
      if(stage + 1 < stages && pipe(edgefd) < 0)
        goto spawn_error;

      pid = fork();
      if(pid < 0){
        if(edgefd[0] >= 0){
          close(edgefd[0]);
          close(edgefd[1]);
        }
        goto spawn_error;
      }
      if(pid == 0)
        run_stage(stage, stages, flow + 1, iterations, deadlines[flow],
                  inputfd, edgefd, releasefd, readyfd, resultfd);

      child_count++;
      if(inputfd >= 0)
        close(inputfd);
      if(edgefd[1] >= 0){
        close(edgefd[1]);
        inputfd = edgefd[0];
      } else {
        inputfd = -1;
      }
    }
    if(inputfd >= 0)
      close(inputfd);
  }

  close(readyfd[1]);
  for(i = 0; i < child_count; i++){
    if(read_full(readyfd[0], &result, 1) != 1)
      goto spawn_error;
  }
  close(readyfd[0]);

  close(releasefd[0]);
  release_tick = (uint)uptime() + 20;
  for(i = 0; i < child_count; i++){
    if(write_full(releasefd[1], &release_tick, sizeof(release_tick)) < 0)
      goto release_error;
  }
  close(releasefd[1]);
  close(resultfd[1]);

  for(i = 0; i < child_count; i++)
    wait();

  completed = 0;
  misses = 0;
  errors = 0;
  for(;;){
    read_result = read_full(resultfd[0], &result, sizeof(result));
    if(read_result == 0)
      break;
    if(read_result < 0){
      errors++;
      break;
    }
    if(result.status != 1){
      printf(1, "BENCH_ERROR wid=%d stage=%d\n", result.wid, result.stage);
      errors++;
      continue;
    }

    completed++;
    if(result.elapsed > (uint)deadlines[result.wid - 1])
      misses++;
    printf(1, "BENCH_RESULT wid=%d stages=%d elapsed=%d deadline=%d miss=%d\n",
           result.wid, stages, result.elapsed, deadlines[result.wid - 1],
           result.elapsed > (uint)deadlines[result.wid - 1]);
  }
  close(resultfd[0]);
  printf(1, "BENCH_SUMMARY workflows=%d completed=%d deadline_misses=%d\n",
         NFLOWS, completed, misses);
  exit();

spawn_error:
  if(inputfd >= 0)
    close(inputfd);
  close(readyfd[0]);
  close(readyfd[1]);
  close(releasefd[0]);
  close(releasefd[1]);
  close(resultfd[1]);
  for(i = 0; i < child_count; i++)
    wait();
  while(read(resultfd[0], &result, sizeof(result)) > 0)
    ;
  close(resultfd[0]);
  printf(2, "sched_bench: pipe or fork failed; spawned children reaped\n");
  exit();

release_error:
  close(releasefd[1]);
  close(resultfd[1]);
  for(i = 0; i < child_count; i++)
    wait();
  while(read(resultfd[0], &result, sizeof(result)) > 0)
    ;
  close(resultfd[0]);
  printf(2, "sched_bench: release failed; spawned children reaped\n");
  exit();
}
