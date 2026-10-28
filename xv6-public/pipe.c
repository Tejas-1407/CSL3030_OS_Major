#include "types.h"
#include "defs.h"
#include "param.h"
#include "mmu.h"
#include "proc.h"
#include "fs.h"
#include "spinlock.h"
#include "sleeplock.h"
#include "file.h"

#define PIPESIZE 512

struct pipe {
  struct spinlock lock;
  char data[PIPESIZE];
  uint nread;     // number of bytes read
  uint nwrite;    // number of bytes written
  int readopen;   // read fd is still open
  int writeopen;  // write fd is still open
  struct proc *writer; // process that most recently wrote to the pipe
};

int
pipealloc(struct file **f0, struct file **f1)
{
  struct pipe *p;

  p = 0;
  *f0 = *f1 = 0;
  if((*f0 = filealloc()) == 0 || (*f1 = filealloc()) == 0)
    goto bad;
  if((p = (struct pipe*)kalloc()) == 0)
    goto bad;
  p->readopen = 1;
  p->writeopen = 1;
  p->nwrite = 0;
  p->nread = 0;
  p->writer = 0;
  initlock(&p->lock, "pipe");
  (*f0)->type = FD_PIPE;
  (*f0)->readable = 1;
  (*f0)->writable = 0;
  (*f0)->pipe = p;
  (*f1)->type = FD_PIPE;
  (*f1)->readable = 0;
  (*f1)->writable = 1;
  (*f1)->pipe = p;
  return 0;

//PAGEBREAK: 20
 bad:
  if(p)
    kfree((char*)p);
  if(*f0)
    fileclose(*f0);
  if(*f1)
    fileclose(*f1);
  return -1;
}

void
pipeclose(struct pipe *p, int writable)
{
  acquire(&p->lock);
  if(writable){
    p->writeopen = 0;
    p->writer = 0;
    wakeup(&p->nread);
  } else {
    p->readopen = 0;
    wakeup(&p->nwrite);
  }
  if(p->readopen == 0 && p->writeopen == 0){
    release(&p->lock);
    kfree((char*)p);
  } else
    release(&p->lock);
}

// Clear the writer pointer when a process closes its last write descriptor.
void
pipewriterclose(struct file *f, struct proc *owner)
{
  int fd;
  int stillopen;
  struct pipe *p;

  if(f->type != FD_PIPE || !f->writable)
    return;

  p = f->pipe;
  acquire(&p->lock);
  if(p->writer == owner){
    stillopen = 0;
    for(fd = 0; fd < NOFILE; fd++){
      if(owner->ofile[fd] &&
         owner->ofile[fd]->type == FD_PIPE &&
         owner->ofile[fd]->writable &&
         owner->ofile[fd]->pipe == p){
        stillopen = 1;
        break;
      }
    }
    if(!stillopen)
      p->writer = 0;
  }
  release(&p->lock);
}

//PAGEBREAK: 40
int
pipewrite(struct pipe *p, char *addr, int n)
{
  int i;
  struct proc *writer = myproc();

  acquire(&p->lock);
  for(i = 0; i < n; i++){
    while(p->nwrite == p->nread + PIPESIZE){  //DOC: pipewrite-full
      if(p->readopen == 0 || myproc()->killed){
        release(&p->lock);
        return -1;
      }
      wakeup(&p->nread);
      sleep(&p->nwrite, &p->lock);  //DOC: pipewrite-sleep
    }
    p->data[p->nwrite++ % PIPESIZE] = addr[i];
    if(i == 0){
      p->writer = writer;
      // PIPE DEPENDENCY DEBUG: remove after validation.
      cprintf("PIPE_WRITE writer=%d\n", writer->pid);
    }
  }
  wakeup(&p->nread);  //DOC: pipewrite-wakeup1
  release(&p->lock);
  return n;
}

int
piperead(struct pipe *p, char *addr, int n)
{
  int i;
  int waited;
  struct proc *reader = myproc();

  waited = 0;
  acquire(&p->lock);
  while(p->nread == p->nwrite && p->writeopen){  //DOC: pipe-empty
    if(myproc()->killed){
      reader->waiting_on = 0;
      release(&p->lock);
      return -1;
    }
    reader->waiting_on = p->writer;
    // PIPE DEPENDENCY DEBUG: remove after validation.
    cprintf("PIPE_WAIT reader=%d writer=%d\n", reader->pid,
            p->writer ? p->writer->pid : -1);
    waited = 1;
    sleep(&p->nread, &p->lock); //DOC: piperead-sleep
  }
  reader->waiting_on = 0;
  if(waited){
    // PIPE DEPENDENCY DEBUG: remove after validation.
    cprintf("PIPE_WAKE reader=%d\n", reader->pid);
  }
  for(i = 0; i < n; i++){  //DOC: piperead-copy
    if(p->nread == p->nwrite)
      break;
    addr[i] = p->data[p->nread++ % PIPESIZE];
  }
  wakeup(&p->nwrite);  //DOC: piperead-wakeup
  release(&p->lock);
  return i;
}
