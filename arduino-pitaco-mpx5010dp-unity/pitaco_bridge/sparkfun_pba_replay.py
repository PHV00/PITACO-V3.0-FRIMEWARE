"""Replay em Python do PBA SparkFun heartRate.cpp (EXPERIMENTAL, offline).

Transcreve aritmetica inteira, FIR de 23 taps, estimador DC, cruzamentos
por zero e amplitude 20..1000. Recebe IR RAW 18 bits e usa IR >> 3, como
o sketch. Nao e teste de acuracia, nao produz SpO2 e NAO altera firmware.
"""
FIR_COEFFS=(172,321,579,927,1360,1858,2390,2916,3391,3768,4012,4096)


class SparkFunPbaReplay:
    def __init__(self):
        self.ac_max=20
        self.ac_min=-20
        self.current=0
        self.maximum=0
        self.minimum=0
        self.positive=0
        self.negative=0
        self.dc_reg=0
        self.buf=[0]*32
        self.offset=0

    def observe(self, ir_raw):
        """Retorna True quando a implementacao SparkFun reconheceria beat."""
        sample=int(ir_raw)>>3
        previous=self.current
        self.dc_reg+=(((sample<<15)-self.dc_reg)>>4)
        average=self.dc_reg>>15
        self.buf[self.offset]=sample-average
        z=FIR_COEFFS[11]*self.buf[(self.offset-11)&31]
        for i in range(11):
            z+=FIR_COEFFS[i]*(self.buf[(self.offset-i)&31]+
                              self.buf[(self.offset-22+i)&31])
        self.offset=(self.offset+1)%32
        self.current=z>>15
        beat=False
        if previous<0 and self.current>=0:
            self.ac_max=self.maximum
            self.ac_min=self.minimum
            self.positive=1
            self.negative=0
            self.maximum=0
            if 20<self.ac_max-self.ac_min<1000:
                beat=True
        if previous>0 and self.current<=0:
            self.positive=0
            self.negative=1
            self.minimum=0
        if self.positive and self.current>previous:
            self.maximum=self.current
        if self.negative and self.current<previous:
            self.minimum=self.current
        return beat


def replay_sparkfun(samples):
    """Conta eventos e intervalos candidatos de BPM, respeitando contato.

    O firmware limita dt entre 300 e 1714 ms; o replay NAO decide G1.
    A equivalencia com hardware depende dos timestamps e amostras completos.
    """
    detector=SparkFunPbaReplay()
    beats=[]
    accepted_intervals=[]
    last_beat=None
    for row in samples:
        red,ir=row["red"],row["ir"]
        optical=(row["contact"] and 5000<=red<260095 and
                 5000<=ir<260095)
        if not optical:
            last_beat=None
            continue
        if detector.observe(ir):
            t=row["t_ms"]
            beats.append(t)
            if last_beat is not None and 300<=t-last_beat<=1714:
                accepted_intervals.append(t-last_beat)
            last_beat=t
    return {"beats_detected":len(beats),
            "bpm_eligible_rr_pairs":len(accepted_intervals),
            "beat_times_ms":beats,
            "eligible_rr_ms":accepted_intervals}
