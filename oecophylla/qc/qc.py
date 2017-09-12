rule qc_atropos:
    """
    Does adapter trimming and read QC with Atropos
    """
    input:
        forward = raw_dir + "{sample}/combined_reads/{sample}.R1.fastq.gz",
        reverse = raw_dir + "{sample}/combined_reads/{sample}.R2.fastq.gz"
    output:
        forward = qc_dir + "{sample}/{trimmer}_trimmed/{sample}.trimmed.R1.fastq.gz",
        reverse = qc_dir + "{sample}/{trimmer}_trimmed/{sample}.trimmed.R2.fastq.gz"
    threads:
        8
    params:
        atropos = config['params']['atropos'],
        env = config['envs']['qc']
    log:
        qc_dir + "logs/qc_atropos.sample=[{sample}].log"
    benchmark:
        "benchmarks/qc/qc_atropos.sample=[{sample}].txt"
    run:
        with tempfile.TemporaryDirectory(dir=find_local_scratch(TMP_DIR_ROOT)) as temp_dir:
            f_fp = os.path.basename(output.forward)
            r_fp = os.path.basename(output.reverse)
            shell("""
                  set +u; {params.env}; set -u
              
                  atropos --threads {threads} {params.atropos} --report-file {log} --report-formats txt -o {temp_dir}/{f_fp} -p {temp_dir}/{r_fp} -pe1 {input.forward} -pe2 {input.reverse}

                  scp {temp_dir}/{f_fp} {output.forward}
                  scp {temp_dir}/{r_fp} {output.reverse}
                  """)

rule qc_filter:
    """
    Performs host read filtering on paired end data using Bowtie and Samtools/
    BEDtools. Takes the four output files generated by Trimmomatic. 

    Also requires an indexed reference (path specified in config). 

    First, uses Bowtie output piped through Samtools to only retain read pairs
    that are never mapped (either concordantly or just singly) to the indexed
    reference genome. Fastqs from this are gzipped into matched forward and 
    reverse pairs. 

    Unpaired forward and reverse reads are simply run through Bowtie and
    non-mapping gzipped reads output.

    All piped output first written to localscratch to avoid tying up filesystem.
    """
    input:
        forward = qc_dir + "{sample}/%s_trimmed/{sample}.trimmed.R1.fastq.gz" % trimmer,
        reverse = qc_dir + "{sample}/%s_trimmed/{sample}.trimmed.R2.fastq.gz" % trimmer
    output:
        forward = qc_dir + "{sample}/filtered/{sample}.R1.trimmed.filtered.fastq.gz",
        reverse = qc_dir + "{sample}/filtered/{sample}.R2.trimmed.filtered.fastq.gz"
    params:
        filter_db = lambda wildcards: config['samples'][wildcards.sample]['filter_db'],
        env = config['envs']['qc']
    threads:
        4
    log:
        bowtie = qc_dir + "logs/qc_filter.bowtie.sample=[{sample}].log",
        other = qc_dir + "logs/qc_filter.other.sample=[{sample}].log"
    benchmark:
         "benchmarks/qc/qc_filter.sample=[{sample}].txt"
    run:
        if params.filter_db is None:
            f_fp = os.path.abspath(input.forward)
            r_fp = os.path.abspath(input.reverse)
            shell("""
                  ln -s {f_fp} {output.forward}
                  ln -s {r_fp} {output.reverse}

                  echo 'No DB provided; sample not filtered.' > {log.bowtie}
                  echo 'No DB provided; sample not filtered.' > {log.other}
                  """)
        else:
            with tempfile.TemporaryDirectory(dir=find_local_scratch(TMP_DIR_ROOT)) as temp_dir:
                shell("""
                      set +u; {params.env}; set -u
          
                      bowtie2 -p {threads} -x {params.filter_db} --very-sensitive -1 {input.forward} -2 {input.reverse} 2> {log.bowtie}| \
                      samtools view -f 12 -F 256 2> {log.other}| \
                      samtools sort -T {temp_dir} -@ {threads} -n 2> {log.other} | \
                      samtools view -bS 2> {log.other} | \
                      bedtools bamtofastq -i - -fq {temp_dir}/{wildcards.sample}.R1.trimmed.filtered.fastq -fq2 {temp_dir}/{wildcards.sample}.R2.trimmed.filtered.fastq 2> {log.other}

                      pigz -c {temp_dir}/{wildcards.sample}.R1.trimmed.filtered.fastq > {temp_dir}/{wildcards.sample}.R1.trimmed.filtered.fastq.gz
                      pigz -c {temp_dir}/{wildcards.sample}.R2.trimmed.filtered.fastq > {temp_dir}/{wildcards.sample}.R2.trimmed.filtered.fastq.gz

                      scp {temp_dir}/{wildcards.sample}.R1.trimmed.filtered.fastq.gz {output.forward}
                      scp {temp_dir}/{wildcards.sample}.R2.trimmed.filtered.fastq.gz {output.reverse} 
                      """)


rule qc_per_sample_fastqc: 
    """
    Makes fastqc reports for each individual input file.
    """
    input:
        forward = qc_dir + "{sample}/filtered/{sample}.R1.trimmed.filtered.fastq.gz",
        reverse = qc_dir + "{sample}/filtered/{sample}.R2.trimmed.filtered.fastq.gz"
    output:
        html = qc_dir + "{sample}/fastqc_per_sample/{sample}.R1.trimmed.filtered_fastqc.html",
        zip = qc_dir + "{sample}/fastqc_per_sample/{sample}.R2.trimmed.filtered_fastqc.zip"
    threads:
        4
    params:
        env = config['envs']['qc']
    log:
        qc_dir + "logs/qc_per_sample_fastqc.sample=[{sample}].log"
    benchmark:
        "benchmarks/qc/qc_per_sample_fastqc.sample=[{sample}].txt"
    run:
        out_dir = os.path.dirname(output[0])
        shell("""
              set +u; {params.env}; set -u
          
              fastqc --threads {threads} --outdir {out_dir} {input.forward} {input.reverse} 2> {log} 1>&2
              """)


rule qc_per_sample_multiqc:
    """
    Runs multiqc for combined input files.
    """
    input:
        expand(qc_dir + "{sample}/fastqc_per_sample/{sample}.R2.trimmed.filtered_fastqc.zip", sample=samples),
    output:
        qc_dir + "multiQC_per_sample/multiqc_report.html"
    threads:
        4
    params:
        env = config['envs']['qc']
    log:
        qc_dir + "logs/qc_per_sample_multiqc.log"
    run:
        out_dir = os.path.dirname(output[0])
        shell("""
              set +u; {params.env}; set -u
          
              multiqc -f -s -o {out_dir} {qc_dir}/*/fastqc_per_sample {qc_dir}/logs 2> {log} 1>&2
              """)


rule qc:
    input:
        expand(qc_dir + "{sample}/{trimmer}_trimmed/{sample}.trimmed.R1.fastq.gz", sample=samples, trimmer=trimmer),
        expand(qc_dir + "{sample}/{trimmer}_trimmed/{sample}.trimmed.R2.fastq.gz", sample=samples, trimmer=trimmer),
        expand(qc_dir + "{sample}/filtered/{sample}.R1.trimmed.filtered.fastq.gz", sample=samples),
        expand(qc_dir + "{sample}/filtered/{sample}.R2.trimmed.filtered.fastq.gz", sample=samples),
        qc_dir + "multiQC_per_sample/multiqc_report.html"

