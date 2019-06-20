import argparse
import json
import sys
from collections import defaultdict

import pexpect

'''
Add alignment "attention" to JSON object using force_align

usage: python add_attention.py fwd_lex fwd_err rev_lex rev_err < input.json
'''

class Aligner:
    # from force_align.py

    def __init__(self, fwd_params, fwd_err, rev_params, rev_err, heuristic='grow-diag-final-and'):
        (fwd_T, fwd_m) = self.read_err(fwd_err)
        (rev_T, rev_m) = self.read_err(rev_err)

        fwd_cmd = ['fast_align', '-i', '-', '-d', '-T', fwd_T, '-m', fwd_m, '-f', fwd_params]
        rev_cmd = ['fast_align', '-i', '-', '-d', '-T', rev_T, '-m', rev_m, '-f', rev_params, '-r']
        tools_cmd = ['atools', '-i', '-', '-j', '-', '-c', heuristic]

        self.fwd_align = pexpect.spawn(' '.join(fwd_cmd))
        self.rev_align = pexpect.spawn(' '.join(rev_cmd))
        self.tools = pexpect.spawn(' '.join(tools_cmd))

        # skip top couple of lines
        temp = ''
        while not temp.startswith('Loaded'):
            temp = self.fwd_align.readline().decode('utf-8')
        temp = ''
        while not temp.startswith('Loaded'):
            temp = self.rev_align.readline().decode('utf-8')

    def align(self, line):
        self.fwd_align.sendline(line)
        self.fwd_align.readline()  # skip input
        fwd_line = self.fwd_align.readline().decode().rstrip()
        self.rev_align.sendline(line)
        self.rev_align.readline(line)  # skip input
        rev_line = self.rev_align.readline().decode().rstrip()

        # f words ||| e words ||| links ||| score
        message = '{}\n{}'.format(fwd_line.split(' ||| ')[2], rev_line.split(' ||| ')[2])

        self.tools.sendline(message)
        self.tools.readline()  # skip 2 lines of input
        self.tools.readline()
        al_line = self.tools.readline().decode().rstrip()

        return al_line

    def close(self):
        self.fwd_align.close()
        self.rev_align.close()
        self.tools.close()

    def read_err(self, err):
        (T, m) = ('', '')
        for line in open(err):
            # expected target length = source length * N
            if 'expected target length' in line:
                m = line.split()[-1]
            # final tension: N
            elif 'final tension' in line:
                T = line.split()[-1]
        return (T, m)


def parse_alignments(align):
    t2s = defaultdict(list)
    for x in align.split(' '):
        s, t = x.split('-')
        t2s[int(t)].append(int(s))
    return t2s


def distribution(n, indices):
    prob = 1 / len(indices) if len(indices) > 0 else 0.0
    a = [0.0 for _ in range(n)]
    for i in indices:
        a[i] = prob
    return a


def parseargs():
    parser = argparse.ArgumentParser()
    parser.add_argument('fwd_params')
    parser.add_argument('fwd_err')
    parser.add_argument('rev_params')
    parser.add_argument('rev_err')
    return parser.parse_args()


def make_bitext(jobj):
    src = jobj["subword_text"]
    tgt = jobj["translation"]
    return src + ' ||| ' + tgt


def main():
    args = parseargs()

    aligner = Aligner(args.fwd_params, args.fwd_err, args.rev_params, args.rev_err, 'grow-diag-final-and')

    for line in sys.stdin:
        jobj = json.loads(line)
        bitext_line = make_bitext(jobj)
        alignments = aligner.align(bitext_line)
        t2s = parse_alignments(alignments)

        src_words = jobj['subword_text'].split()
        tgt_words = jobj['translation'].split()
        attention = []

        for i, _word in enumerate(tgt_words):
            att = distribution(len(src_words), t2s.get(i, []))
            attention.append(att)

        jobj['alignment'] = attention
        print(json.dumps(jobj))

    aligner.close()


if __name__ == '__main__':
    main()