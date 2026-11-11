#include "types.h"
#include "stat.h"
#include "user.h"

int
main(int argc, char *argv[])
{
  int data[2], writer_ready[2], reader_ready[2];
  int writer_go[2], competitor_ready[2], competitor_go[2];
  int reader_pid, pid, waited_pid;
  char token, prime;

  if(pipe(data) < 0 || pipe(writer_ready) < 0 ||
     pipe(reader_ready) < 0 || pipe(writer_go) < 0 ||
     pipe(competitor_ready) < 0 || pipe(competitor_go) < 0){
    printf(1, "donation_kill_test: pipe creation failed\n");
    exit();
  }

  pid = fork();
  if(pid < 0){
    printf(1, "donation_kill_test: fork writer failed\n");
    exit();
  }
  if(pid == 0){
    close(data[0]);
    close(writer_ready[0]);
    close(reader_ready[0]);
    close(reader_ready[1]);
    close(writer_go[1]);
    close(competitor_ready[0]);
    close(competitor_ready[1]);
    close(competitor_go[0]);
    close(competitor_go[1]);
    if(setworkflow(1, 300) < 0)
      exit();

    prime = 'p';
    if(write(data[1], &prime, 1) != 1)
      exit();
    token = 'w';
    if(write(writer_ready[1], &token, 1) != 1)
      exit();
    close(writer_ready[1]);

    if(read(writer_go[0], &token, 1) != 1)
      exit();
    printf(1, "WRITER_RUN pid=%d deadline=300\n", getpid());
    close(data[1]);
    close(writer_go[0]);
    exit();
  }

  close(data[1]);
  close(writer_ready[1]);
  close(writer_go[0]);

  if(read(writer_ready[0], &token, 1) != 1){
    printf(1, "donation_kill_test: writer did not prime pipe\n");
    exit();
  }
  close(writer_ready[0]);

  pid = fork();
  if(pid < 0){
    printf(1, "donation_kill_test: fork reader failed\n");
    exit();
  }
  if(pid == 0){
    close(writer_ready[0]);
    close(writer_ready[1]);
    close(reader_ready[0]);
    close(writer_go[1]);
    close(competitor_ready[0]);
    close(competitor_ready[1]);
    close(competitor_go[0]);
    close(competitor_go[1]);
    if(setworkflow(2, 100) < 0)
      exit();

    if(read(data[0], &prime, 1) != 1)
      exit();
    token = 'r';
    if(write(reader_ready[1], &token, 1) != 1)
      exit();
    close(reader_ready[1]);

    read(data[0], &token, 1);
    close(data[0]);
    exit();
  }
  reader_pid = pid;
  close(reader_ready[1]);

  if(read(reader_ready[0], &token, 1) != 1){
    printf(1, "donation_kill_test: reader did not become ready\n");
    exit();
  }
  close(reader_ready[0]);

  if(kill(reader_pid) < 0){
    printf(1, "donation_kill_test: kill failed\n");
    exit();
  }
  waited_pid = wait();
  if(waited_pid != reader_pid){
    printf(1, "donation_kill_test: reader cleanup was not reaped\n");
    exit();
  }
  printf(1, "DONOR_KILLED pid=%d\n", reader_pid);

  pid = fork();
  if(pid < 0){
    printf(1, "donation_kill_test: fork competitor failed\n");
    exit();
  }
  if(pid == 0){
    close(data[0]);
    close(writer_go[1]);
    close(competitor_ready[0]);
    close(competitor_go[1]);
    if(setworkflow(3, 200) < 0)
      exit();
    token = 'c';
    if(write(competitor_ready[1], &token, 1) != 1)
      exit();
    close(competitor_ready[1]);
    if(read(competitor_go[0], &token, 1) != 1)
      exit();
    printf(1, "COMPETITOR_RUN pid=%d deadline=200\n", getpid());
    close(competitor_go[0]);
    exit();
  }

  close(data[0]);
  close(writer_go[0]);
  close(competitor_ready[1]);
  close(competitor_go[0]);
  if(read(competitor_ready[0], &token, 1) != 1){
    printf(1, "donation_kill_test: competitor did not become ready\n");
    exit();
  }
  close(competitor_ready[0]);

  token = 'g';
  if(write(writer_go[1], &token, 1) != 1 ||
     write(competitor_go[1], &token, 1) != 1){
    printf(1, "donation_kill_test: release failed\n");
    exit();
  }
  close(writer_go[1]);
  close(competitor_go[1]);

  wait();
  wait();
  printf(1, "donation_kill_test: complete\n");
  exit();
}
