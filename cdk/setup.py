import setuptools

from domino_cdk import __version__

with open("README.md") as fp:
    long_description = fp.read()


setuptools.setup(
    name="domino-cdk",
    version=__version__,
    description="Domino CDK Stacks",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Domino Data Lab",
    packages=["domino_cdk"],
    package_data={"domino_cdk": ["config_template.yaml"]},
    data_files=[
        ("domino-cdk", ["app.py"]),
    ],
    install_requires=[
        "aws-cdk.core==1.97.0",
        "aws-cdk.aws_s3==1.97.0",
        "aws-cdk.aws_ec2==1.97.0",
        "aws-cdk.aws_ecr==1.97.0",
        "aws-cdk.aws_eks==1.97.0",
        "aws-cdk.aws_efs==1.97.0",
        "aws-cdk.aws_iam==1.97.0",
        "aws_cdk.aws_lambda==1.97.0",
        "aws_cdk.lambda_layer_kubectl==1.97.0",
        "aws_cdk.lambda_layer_awscli==1.97.0",
        "aws_cdk.aws_stepfunctions_tasks==1.97.0",
        "aws_cdk.aws_backup==1.97.0",
        "requests==2.25.1",
        "black==21.4b2",
        "PyYAML==5.4.1",
        "isort==5.8.0",
        "flake8==3.9.1",
    ],
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: JavaScript",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",
        "Typing :: Typed",
    ],
)
